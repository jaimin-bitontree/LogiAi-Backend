from agent.state import AgentState
from models.shipment import Message, Shipment
from services.shipment_service import create_shipment, find_by_thread_id
from utils.req_id_generator import generate_request_id


async def generate_reqid(state: AgentState) -> AgentState:
    thread_id = state.get("thread_id")

    if thread_id:
        existing_shipment = await find_by_thread_id(thread_id)

        if existing_shipment:
            # Update state from DB
            state["request_id"] = existing_shipment.request_id
            state["status"] = existing_shipment.status
            state["intent"] = existing_shipment.intent
            state["message_ids"] = existing_shipment.message_ids
            state["attachments"] = existing_shipment.attachments
            return state

    else:
        if state.get("request_id"):
            return state
        new_request_id = generate_request_id()
        state["request_id"] = new_request_id
        state["status"] = "NEW"

        message = Message(
                        message_id=(
                            state["message_ids"][0]
                            if state.get("message_ids")
                            else ""
                            ),
                        sender_email=state["customer_email"],
                        sender_type="customer",
                        direction="incoming",
                        subject=state.get("subject"),
                        body=state.get("body", ""),
                        attachments=state.get("attachments") or {},
                    )
        
        message_ids = state.get("message_ids")

        if not isinstance(message_ids, list):
            message_ids = []

        shipment = Shipment(
                        request_id=new_request_id,
                        thread_id=thread_id,
                        customer_email=state["customer_email"],
                        subject=state.get("subject"),
                        attachments=state.get("attachments") or {},
                        messages=[message],
                        message_ids=message_ids,
                    )
        await create_shipment(shipment)

        return state
