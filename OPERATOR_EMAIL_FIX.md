# Operator Email Fix

## Problem

When the operator sent a pricing email, it was being treated as a NEW request instead of matching the existing shipment.

## Root Cause

The workflow was routing operator emails directly from `parser_node` to `pricing_node`, **skipping the `reqid_generator_node` entirely**.

### Old Workflow (Broken):
```
Operator Email:
  parser_node → pricing_node (❌ No shipment lookup!)
  
Customer Email:
  parser_node → language_node → intent_node → reqid_node → extraction_node
```

This meant:
- Operator emails never went through shipment lookup
- No matching to existing conversations
- Always treated as new requests
- `request_id` was empty in state

## Solution

Changed the workflow so ALL emails (customer and operator) go through `reqid_generator_node` first.

### New Workflow (Fixed):
```
ALL Emails:
  parser_node → reqid_node → [route based on is_operator]
  
If is_operator=True:
  reqid_node → pricing_node
  
If is_operator=False:
  reqid_node → language_node → intent_node → extraction_node
```

## Changes Made

### 1. Updated Workflow Routing (`agent/workflow.py`)

**Before:**
```python
def route_after_parser(state: AgentState):
    if state.get("is_operator"):
        return "pricing"  # ❌ Skips reqid lookup!
    return "language"

builder.add_edge(START, "parser")
builder.add_conditional_edges("parser", route_after_parser, {...})
builder.add_edge("language", "intent")
builder.add_edge("intent", "reqid")
builder.add_edge("reqid", "extraction")
```

**After:**
```python
# All emails go through reqid first
builder.add_edge(START, "parser")
builder.add_edge("parser", "reqid")

def route_after_reqid(state: AgentState):
    """Route after reqid_generator_node based on sender type."""
    if state.get("is_operator"):
        return "pricing"
    return "language"

builder.add_conditional_edges("reqid", route_after_reqid, {...})
builder.add_edge("language", "intent")
builder.add_edge("intent", "extraction")
```

### 2. Fixed Message Builder (`agent/nodes/reqid_generator_node.py`)

**Before:**
```python
def _build_message(state: AgentState):
    return Message(
        sender_type="customer",  # ❌ Always customer!
        ...
    )
```

**After:**
```python
def _build_message(state: AgentState):
    is_operator = state.get("is_operator", False)
    return Message(
        sender_type="operator" if is_operator else "customer",  # ✅ Correct type
        ...
    )
```

## How It Works Now

### Scenario: Operator Sends Pricing

```
┌─────────────────────────────────────────────────────────────┐
│ 1. System sends notification to operator                    │
└─────────────────────────────────────────────────────────────┘

DB State:
  {
    request_id: "REQ-2024-001",
    thread_id: "MSG001",
    last_message_id: "MSG003",  ← Operator notification
    message_ids: ["MSG001", "MSG002", "MSG003"],
    status: "PRICING_PENDING"
  }

┌─────────────────────────────────────────────────────────────┐
│ 2. Operator replies with pricing                            │
└─────────────────────────────────────────────────────────────┘

📧 Email Arrives:
   Message-ID: MSG004
   In-Reply-To: MSG003
   From: operator@company.com
   Body: "Pricing details..."

┌─────────────────────────────────────────────────────────────┐
│ parse_node                                                   │
└─────────────────────────────────────────────────────────────┘
State:
   thread_id = MSG004
   conversation_id = MSG003
   customer_email = operator@company.com
   is_operator = True  ✅

┌─────────────────────────────────────────────────────────────┐
│ reqid_generator_node (NOW RUNS FOR OPERATOR!)               │
└─────────────────────────────────────────────────────────────┘
Lookup Steps:
   Step 1: Dedup → message_ids contains MSG004? NO
   Step 2: Thread root → thread_id == MSG003? NO
   Step 3: Any message ✅
           → message_ids contains MSG003?
           → ["MSG001", "MSG002", "MSG003"]
           → MSG003 found! ✅ MATCH

FOUND SHIPMENT: REQ-2024-001

update_shipment_thread_id():
   DB Updated:
   {
     request_id: "REQ-2024-001",
     thread_id: "MSG001",           ← Unchanged
     last_message_id: "MSG004",     ← Updated
     message_ids: ["MSG001", "MSG002", "MSG003", "MSG004"],
     status: "PRICING_PENDING"
   }

State Hydrated:
   request_id = "REQ-2024-001"  ✅ (was empty before!)
   status = "PRICING_PENDING"
   All existing shipment data loaded

┌─────────────────────────────────────────────────────────────┐
│ route_after_reqid                                            │
└─────────────────────────────────────────────────────────────┘
is_operator = True → Route to pricing_node

┌─────────────────────────────────────────────────────────────┐
│ pricing_node                                                 │
└─────────────────────────────────────────────────────────────┘
Now has access to:
   ✅ request_id = "REQ-2024-001"
   ✅ customer_email from DB
   ✅ All shipment data
   
Can extract pricing and send quote to customer!
```

## Benefits

### Before Fix:
- ❌ Operator email treated as new request
- ❌ No request_id in state
- ❌ Can't find customer to send quote to
- ❌ Creates duplicate/orphaned records

### After Fix:
- ✅ Operator email matched to existing shipment
- ✅ request_id loaded from DB
- ✅ Customer email available
- ✅ Quote sent successfully
- ✅ Proper conversation threading

## Testing Checklist

- [ ] Customer sends complete request
- [ ] System sends to operator
- [ ] Operator replies with pricing
- [ ] System matches to correct shipment
- [ ] Quote sent to customer
- [ ] No duplicate shipments created
- [ ] Message history preserved correctly
- [ ] sender_type="operator" in messages array

## Key Insight

The `reqid_generator_node` is not just for generating request IDs—it's the **conversation matching engine**. ALL emails must go through it to:
1. Match replies to existing conversations
2. Hydrate state with shipment data
3. Update message history
4. Maintain thread integrity

Skipping it for operator emails broke the entire conversation flow.
