# LogiAI System Architecture Documentation

## Overview

LogiAI is an AI-powered logistics email automation system that processes shipment requests, extracts information, manages conversations, and automates responses using LLM-based agents.

**Tech Stack:**
- Backend: FastAPI (Python async)
- Database: MongoDB
- AI Framework: LangChain + LangGraph
- LLM Provider: Groq API (Llama models)
- Email: Gmail IMAP/SMTP

---

## System Flow

### Phase 1: Email Polling
**File:** `utils/poller.py`

- Background job polls Gmail every 60 seconds
- Fetches unread emails via IMAP
- Marks emails as read
- Passes raw RFC822 bytes to workflow

### Phase 2: Pre-Processing Pipeline (Fixed Sequence)
**File:** `agent/workflow.py`

**1. Parser Node** (`agent/nodes/parse_node.py`)
- Extracts: subject, sender, body, Message-ID, In-Reply-To
- Processes PDF/Excel attachments (appends text to body)
- Detects operator emails
- Looks up existing shipments for operator replies

**2. Language Node** (`agent/nodes/language_node.py`)
- Detects language (body + subject)
- Translates to English if needed
- Model: `llama-3.1-8b-instant`

**3. Intent Node** (`agent/nodes/intent_node.py`)
- Classifies email intent:
  - `new_request` - Customer requesting quotation
  - `missing_information` - Reply with missing fields
  - `status_inquiry` - Asking about shipment status
  - `confirmation` - Accepting quotation
  - `cancellation` - Canceling shipment
  - `operator_pricing` - Operator providing pricing
- Extracts request_id from email body
- Model: `llama-3.1-8b-instant`

**4. Request ID Generator** (`agent/nodes/reqid_generator_node.py`)
- Multi-strategy shipment lookup:
  1. Check if message already processed (deduplication)
  2. Lookup by In-Reply-To header (conversation threading)
  3. Lookup by message_ids array (any message in conversation)
  4. Lookup by request_id extracted from email body
  5. Lookup by customer email + open status
  6. Generate new request_id if not found
- Creates/updates shipment in MongoDB
- Merges conversation history (old body + new body)

**5. Context Builder** (`agent/nodes/context_builder_node.py`)
- Builds HumanMessage for agent with:
  - Request ID
  - Customer email
  - Intent
  - Action directive
  - Email snippet (full body for operator_pricing)
- Seeds the agentic loop

### Phase 3: Agentic Loop (LLM-Driven)
**File:** `agent/agent_node.py`

**Agent Node:**
- Model: `llama-3.3-70b-versatile` (only reliable tool-calling model)
- Temperature: 0.0 (deterministic)
- Binds 9 tools
- System prompt instructs:
  - Which tool to use for each intent
  - When to STOP (after email tools)
  - How to extract parameters

**Tool Node:**
- Executes tools asynchronously
- Returns ToolMessage with results
- Sets `email_tool_executed` flag for email tools

**Workflow Control** (`should_continue`):
- Checks if email tool executed → END
- Checks for duplicate tool calls → END
- Checks if agent has more tool_calls → LOOP BACK
- Otherwise → END

---

## Tools (9 Total)

### Extraction Tools
**1. extract_shipment_fields** (`agent/tools/extraction_tool.py`)
- Extracts all fields from new shipment request
- Model: `llama-3.1-8b-instant`
- Validates required fields
- DB: Updates `shipment.request_data`

**2. extract_missing_field_values** (`agent/tools/extraction_tool.py`)
- Extracts specific missing fields from reply
- Model: `llama-3.1-8b-instant`
- Merges with existing data
- DB: Updates `shipment.request_data`

### Email Tools
**3. send_missing_info_email** (`agent/tools/email_tools.py`)
- Sends email requesting missing fields
- DB: Logs message, updates status to `MISSING_INFO`

**4. send_complete_info_emails** (`agent/tools/email_tools.py`)
- Sends 2 emails:
  1. Customer confirmation (all info received)
  2. Operator notification (new request for pricing)
- DB: Logs both messages, updates status to `PRICING_PENDING`

### Pricing Tools
**5. calculate_and_send_pricing** (`agent/tools/pricing_tools.py`)
- Extracts pricing from operator email
- Model: `llama-3.1-8b-instant`
- Sends quotation to customer
- DB: Saves `pricing_details`, logs message, updates status to `QUOTED`

### Status Tools
**6. send_status_update** (`agent/tools/status_tools.py`)
- Fetches current shipment status
- Sends status email to customer
- DB: Logs message

**7. update_shipment_status** (`agent/tools/status_tools.py`)
- Updates shipment status in database
- DB: Updates `shipment.status`

### Confirmation Tools
**8. process_shipment_confirmation** (`agent/tools/confirmation_tools.py`)
- Handles customer acceptance of quotation
- DB: Updates status to `CONFIRMED`, logs message

### Cancellation Tools
**9. cancel_shipment** (`agent/tools/cancellation_tools.py`)
- Processes cancellation request
- DB: Updates status to `CANCELLED`, logs message

---

## Database Schema

### Collection: `shipments`

```javascript
{
  // Identity
  request_id: "REQ-2026-0310123456",
  thread_id: "LOGIAI-REQ-2026-0310123456-1773123456@logiai.com",  // First message (never changes)
  last_message_id: "LOGIAI-REQ-2026-0310123456-1773123789@logiai.com",  // Latest message
  customer_email: "customer@example.com",
  
  // Email Content
  subject: "Shipment Request",
  body: "Merged conversation history...",  // All emails concatenated
  translated_body: "English version",
  translated_subject: "English subject",
  
  // Classification
  intent: "new_request | missing_information | status_inquiry | confirmation | cancellation | operator_pricing",
  status: "NEW | MISSING_INFO | PRICING_PENDING | QUOTED | CONFIRMED | CANCELLED",
  
  // Language
  language_metadata: {
    detected_language: "en",
    confidence: 0.95,
    translated_to_english: false,
    subject_translated_to_english: false
  },
  
  // Extracted Data
  request_data: {
    required: {
      customer_name: "Orion Electronics",
      origin_city: "Mumbai",
      origin_country: "India",
      destination_city: "Hamburg",
      destination_country: "Germany",
      // ... 13 required fields total
    },
    optional: {
      contact_person_name: "Rahul Mehta",
      // ... 13 optional fields total
    }
  },
  
  // Validation
  validation_result: {
    is_valid: false,
    missing_fields: ["volume", "container_type"]
  },
  
  // Pricing
  pricing_details: [
    {
      transport_mode: "Sea",
      pricing_type: "FCL",
      main_freight_charges: [
        { description: "Ocean Freight", amount: "1650", currency: "USD" }
      ],
      origin_charges: [...],
      destination_charges: [...],
      // ... full pricing schema
    }
  ],
  
  // Conversation History
  messages: [
    {
      message_id: "LOGIAI-...",
      sender_email: "customer@example.com",
      sender_type: "customer | system | operator",
      direction: "incoming | outgoing",
      subject: "...",
      body: "...",
      received_at: ISODate("2026-03-10T10:00:00Z"),
      attachments: [...]
    }
  ],
  
  // Threading
  message_ids: ["id1", "id2", "id3"],  // All message IDs in conversation
  
  // Attachments
  attachments: [
    {
      filename: "document.pdf",
      content_type: "application/pdf",
      content: null  // Binary data not stored in DB
    }
  ],
  
  // Metadata
  is_operator: false,
  created_at: ISODate("2026-03-10T10:00:00Z"),
  updated_at: ISODate("2026-03-10T10:05:00Z")
}
```

---

## Models Used

### 1. llama-3.3-70b-versatile (Groq)
**Usage:** Agent tool calling
**File:** `agent/agent_node.py`
**Why:** Only reliable model for tool calling with LangChain
**Fallback:** None (critical path)

### 2. llama-3.1-8b-instant (Groq)
**Usage:**
- Language detection & translation
- Intent classification
- Field extraction (shipment data)
- Pricing extraction

**Files:**
- `services/language_service.py`
- `services/intent_service.py`
- `services/extraction_service.py`
- `services/pricing_service.py`

**Why:** Fast, cheap, good for structured extraction
**Config:** `EXTRACTION_MODEL`, `LANGUAGE_DETECT_MODEL`

---

## State Management

### AgentState (TypedDict)
**File:** `agent/state.py`

```python
{
    # Email Identity
    "raw_email": bytes,
    "request_id": str,
    "thread_id": str,              # Message-ID (conversation root)
    "conversation_id": str,        # In-Reply-To
    "last_message_id": str,        # Latest message
    "customer_email": str,
    "subject": str,
    "message_ids": List[str],
    
    # Content
    "body": str,                   # Merged conversation
    "translated_body": str,
    "translated_subject": str,
    "attachments": List[Attachment],
    
    # Classification
    "status": str,
    "intent": str,
    "is_operator": bool,
    "shipment_found": bool,
    
    # Language
    "language_metadata": LanguageMetadata,
    
    # Extracted Data
    "request_data": Dict,
    "validation_result": ValidationResult,
    "pricing_details": List[PricingSchema],
    
    # LangChain Messages (append-only)
    "messages": Annotated[List[BaseMessage], add_messages],
    
    # Workflow Control
    "email_tool_executed": bool,
    "final_document": str
}
```

**State Updates:**
- Each node returns a dict
- LangGraph merges into state
- `messages` field uses `add_messages` reducer (append-only)

---

## Key Design Patterns

### 1. Self-Contained Tools
- Tools fetch their own data from DB
- Agent only passes small scalar args (request_id, email)
- No large dict payloads in tool calls
- Reduces token usage and improves reliability

### 2. Conversation Threading
- `thread_id` = first message (conversation root, never changes)
- `last_message_id` = latest message (always updated)
- `message_ids` = array of all messages in conversation
- Body merging preserves full conversation history
- Enables proper email threading and reply detection

### 3. Workflow Termination
- Multiple layers of protection:
  - Flag-based: `email_tool_executed` state flag
  - Content-based: Detects email indicators in ToolMessage
  - Duplicate prevention: Prevents same tool being called twice
- Email tools are terminal actions
- Agent system prompt instructs to STOP after sending emails

### 4. Error Handling
- **API Key Rotation:** 3 Groq API keys (GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3)
- **Model Fallback:** Only 70b for tool calling (8b unreliable)
- **Retry Logic:** 2 attempts for transient errors
- **Graceful Degradation:** Returns error messages instead of crashing

### 5. Operator Email Detection
- Multi-strategy lookup:
  1. In-Reply-To header (most reliable for replies)
  2. Request ID in subject line
  3. Request ID in body
- Hydrates state with existing shipment data
- Overrides customer_email with actual customer

---

## Example Flows

### Flow 1: New Request with Missing Fields

```
1. Email: "I need quote for shipment from Mumbai to Hamburg"
2. PARSER: Extracts email
3. LANGUAGE: English detected, no translation
4. INTENT: Classifies as "new_request"
5. REQID: Generates REQ-2026-0310123456
6. CONTEXT BUILDER: Seeds agent
7. AGENT: Calls extract_shipment_fields()
8. TOOL: Finds missing: volume, container_type
9. AGENT: Calls send_missing_info_email()
10. TOOL: Sends email, updates DB status=MISSING_INFO
11. WORKFLOW: Detects email tool → END
```

### Flow 2: Customer Replies with Missing Info

```
1. Email: "Volume: 18 CBM, Container Type: 20' GP"
2. PARSER: Extracts, finds In-Reply-To header
3. LANGUAGE: English, no translation
4. INTENT: Classifies as "missing_information"
5. REQID: Finds existing shipment by In-Reply-To
6. CONTEXT BUILDER: Seeds with missing_fields
7. AGENT: Calls extract_missing_field_values()
8. TOOL: Extracts fields, merges with existing data
9. AGENT: Calls send_complete_info_emails()
10. TOOL: Sends 2 emails (customer + operator)
11. WORKFLOW: Detects email tool → END
```

### Flow 3: Operator Provides Pricing

```
1. Email: "Ocean Freight: USD 1,650, BAF: USD 190..."
2. PARSER: Detects operator email, looks up by In-Reply-To
3. LANGUAGE: English, no translation
4. INTENT: Classifies as "operator_pricing"
5. REQID: Finds existing shipment
6. CONTEXT BUILDER: Seeds with FULL body (for extraction)
7. AGENT: Calls calculate_and_send_pricing()
8. TOOL: Extracts pricing data, saves to DB
9. TOOL: Sends quotation email to customer
10. WORKFLOW: Detects email tool → END
```

### Flow 4: Customer Confirms Quote

```
1. Email: "REQ-2026-0310123456 accepted"
2. PARSER: Extracts email
3. LANGUAGE: English, no translation
4. INTENT: Classifies as "confirmation"
5. REQID: Finds existing shipment by request_id
6. CONTEXT BUILDER: Seeds agent
7. AGENT: Calls process_shipment_confirmation()
8. TOOL: Updates status=CONFIRMED, sends confirmation
9. WORKFLOW: Detects email tool → END
```

---

## Configuration

### Environment Variables (.env)

```bash
# Database
MONGODB_URI=mongodb+srv://...
DB_NAME=logiai_db

# Email
GMAIL_ADDRESS=logiai2026@gmail.com
GMAIL_APP_PASSWORD=...
IMAP_GMAIL=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SYSTEM_EMAIL=logiai2026@gmail.com
OPERATOR_EMAIL=op1.logiai@gmail.com

# Groq API (3 keys for rotation)
GROQ_API_KEY=gsk_...
GROQ_API_KEY_2=gsk_...
GROQ_API_KEY_3=gsk_...

# Models
LANGUAGE_DETECT_MODEL=llama-3.1-8b-instant
LANGUAGE_TRANSLATE_MODEL=llama-3.1-8b-instant
EXTRACTION_MODEL=llama-3.1-8b-instant

# Thresholds
LANGUAGE_CONFIDENCE_THRESHOLD=0.85
```

### Required Fields (13)
- customer_name, customer_street_number, customer_zip_code, customer_country
- origin_zip_code, origin_city, origin_country
- destination_zip_code, destination_city, destination_country
- incoterm, quantity, package_type, cargo_weight, volume, container_type
- transport_mode, shipment_type

### Optional Fields (13)
- contact_person_name, contact_person_email, contact_person_phone
- customer_reference, origin_company, origin_street_number
- destination_company, destination_street_number
- description_of_goods, additional_information
- stackable, dangerous, temperature, length, height, width

---

## File Structure

```
Backend/
├── agent/
│   ├── nodes/
│   │   ├── parse_node.py           # Email parsing & attachment extraction
│   │   ├── language_node.py        # Language detection & translation
│   │   ├── intent_node.py          # Intent classification
│   │   ├── reqid_generator_node.py # Request ID generation & lookup
│   │   └── context_builder_node.py # Agent message seeding
│   ├── tools/
│   │   ├── extraction_tool.py      # Field extraction tools
│   │   ├── email_tools.py          # Email sending tools
│   │   ├── pricing_tools.py        # Pricing extraction & sending
│   │   ├── status_tools.py         # Status update tools
│   │   ├── confirmation_tools.py   # Confirmation handling
│   │   └── cancellation_tools.py   # Cancellation handling
│   ├── agent_node.py               # Main LLM agent with tool calling
│   ├── state.py                    # AgentState TypedDict definition
│   └── workflow.py                 # LangGraph workflow orchestration
├── services/
│   ├── language_service.py         # Language detection & translation
│   ├── intent_service.py           # Intent classification
│   ├── extraction_service.py       # Field extraction
│   ├── pricing_service.py          # Pricing extraction
│   ├── status_service.py           # Status lookup
│   ├── shipment_service.py         # Core CRUD operations
│   ├── email_sender.py             # SMTP email sending
│   └── gmail_receiver.py           # IMAP email fetching
├── api/
│   ├── shipment_router.py          # FastAPI endpoints
│   └── shipment_service.py         # API service layer
├── db/
│   └── client.py                   # MongoDB connection
├── utils/
│   ├── poller.py                   # Email polling background job
│   ├── email_utils.py              # Email parsing utilities
│   ├── email_template.py           # HTML email templates
│   ├── attachment_helper.py        # PDF/Excel extraction
│   └── req_id_generator.py         # Request ID generation
├── models/
│   └── shipment.py                 # Pydantic models
├── core/
│   └── constants.py                # Field definitions
├── config.py                       # Settings & configuration
├── main.py                         # FastAPI app entry point
└── .env                            # Environment variables
```

---

## API Endpoints

### FastAPI Routes (`api/shipment_router.py`)

```python
GET  /shipments                    # List all shipments
GET  /shipments/{request_id}       # Get shipment by ID
POST /shipments                    # Create shipment (manual)
PUT  /shipments/{request_id}       # Update shipment
DELETE /shipments/{request_id}     # Delete shipment
```

---

## Monitoring & Debugging

### Log Levels
- `INFO`: Normal operations, tool calls, email sending
- `WARNING`: Rate limits, lookup failures, retries
- `ERROR`: Critical failures, all API keys exhausted
- `DEBUG`: Detailed extraction results, state updates

### Key Log Messages
```
[parser_node] Extracting PDF: document.pdf
[language_node] Detected language: es (confidence: 0.92)
[intent_node] Classified intent: new_request
[reqid_generator_node] Step 2 HIT — matched by In-Reply-To
[agent_node] Success with llama-3.3-70b-versatile
[email_tools] Both emails sent | customer_msg_id=... | operator_msg_id=...
[workflow] Email tool executed flag detected, ending workflow
```

### Debug Mode
Add print statements in tools to see:
- Email body length and preview
- Extraction results
- Database operations
- Tool execution flow

---

## Performance Considerations

### Token Usage
- Context builder provides snippets (200 chars) for most intents
- Full body only for operator_pricing (needs complete pricing data)
- Self-contained tools reduce payload size
- Average tokens per request: ~2,000-5,000

### API Rate Limits
- Groq Free Tier: 30 requests/minute per key
- 3 keys = 90 requests/minute total
- Automatic rotation on rate limit
- Retry logic for transient errors

### Database Queries
- Indexed fields: request_id, customer_email, message_ids
- Conversation lookup: O(1) by In-Reply-To
- Body merging: Appends new content to existing

---

## Future Enhancements

1. **Attachment Storage:** Store PDF/Excel files in cloud storage
2. **Multi-Language Support:** Improve translation quality
3. **Pricing Validation:** Validate extracted pricing against rules
4. **Analytics Dashboard:** Track metrics, conversion rates
5. **Webhook Integration:** Real-time notifications
6. **Email Templates:** Customizable templates per customer
7. **Approval Workflow:** Manual review before sending quotes
8. **Audit Trail:** Track all changes to shipments

---

## Troubleshooting

### Issue: Infinite Loop (Duplicate Emails)
**Cause:** Workflow not stopping after email tool
**Fix:** Check `email_tool_executed` flag, verify tool name in list

### Issue: Intent Misclassification
**Cause:** Ambiguous email content
**Fix:** Improve intent prompt with more examples

### Issue: Extraction Failures
**Cause:** Truncated body, poor email formatting
**Fix:** Ensure full body passed for operator_pricing

### Issue: Rate Limits
**Cause:** All API keys exhausted
**Fix:** Add more keys, wait 8-10 minutes, upgrade to Dev Tier

### Issue: Operator Email Not Found
**Cause:** In-Reply-To header missing or incorrect
**Fix:** Check email threading, verify Message-ID format

---

**Last Updated:** March 10, 2026
**Version:** 1.0
**Maintainer:** LogiAI Team
