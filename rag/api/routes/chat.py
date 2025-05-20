# rag/api/routes/chat.py
import asyncio
import logging
import json # For NDJSON
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from rag.api.models import GenAIChatRequest, GenAIChatResponseChunk, ChatMessagePy

logger = logging.getLogger("chat_routes")
router = APIRouter(tags=["Chat"])

# NEW: Minimal stream generator for testing
async def generate_minimal_stream_for_debug():
    try:
        chunk1_data = {"text": "DebugChunk1 ", "done": False, "error": None}
        chunk1_str = json.dumps(chunk1_data) + "\\n"
        logger.info(f"Yielding DEBUG chunk 1: {chunk1_str!r}")
        yield chunk1_str
        await asyncio.sleep(0.1)

        chunk2_data = {"text": "DebugChunk2", "done": True, "error": None}
        chunk2_str = json.dumps(chunk2_data) + "\\n"
        logger.info(f"Yielding DEBUG chunk 2: {chunk2_str!r}")
        yield chunk2_str
    except Exception as e:
        logger.error(f"Error in generate_minimal_stream_for_debug: {e}", exc_info=True)
        error_chunk_data = {"text": "", "done": True, "error": f"Error in debug stream: {e}"}
        yield json.dumps(error_chunk_data) + "\\n"

async def generate_simulated_llm_stream(messages: list[ChatMessagePy], model: str | None):
    """
    Simulates an LLM generating a response by streaming words from the last user message.
    Each word is a chunk in NDJSON format.
    """
    logger.info(f"Simulating LLM response for model: {model or 'default'}")
    
    last_user_message_content = "No user message found."
    for msg in reversed(messages):
        if msg.role == "user":
            last_user_message_content = msg.content
            break

    response_prefix = f"Model \'{model or 'default'}\' responding to: "
    full_simulated_response = response_prefix + last_user_message_content
    
    words = full_simulated_response.split()

    if not words: # Handle empty message
        try:
            chunk_data = GenAIChatResponseChunk(text="", done=True)
            json_chunk_str = json.dumps(chunk_data.model_dump()) + "\\n"
            logger.info(f"Yielding empty message chunk: {json_chunk_str!r}")
            yield json_chunk_str
            return
        except Exception as e:
            logger.error(f"Error yielding empty message chunk: {e}", exc_info=True)
            # Fallback error chunk
            error_chunk_data = {"text": "", "done": True, "error": f"Error in empty message: {e}"}
            yield json.dumps(error_chunk_data) + "\\n"
            return


    for i, word in enumerate(words):
        is_done = i == len(words) - 1
        try:
            chunk_data = GenAIChatResponseChunk(text=word + " ", done=is_done)
            # Convert Pydantic model to dict, then to JSON string, then add newline for NDJSON
            json_chunk_str = json.dumps(chunk_data.model_dump()) + "\\n" # Use model_dump() for Pydantic v2
            logger.info(f"Yielding chunk ({i+1}/{len(words)}): {json_chunk_str!r}")
            yield json_chunk_str
            await asyncio.sleep(0.1) # Simulate delay
        except Exception as e:
            logger.error(f"Error yielding chunk {i+1}: {e}", exc_info=True)
            # Attempt to yield a final error chunk if loop iteration fails
            error_chunk_data = {"text": "", "done": True, "error": f"Error in word chunk {i+1}: {e}"}
            yield json.dumps(error_chunk_data) + "\\n"
            return # Stop further processing

    # This final "done" message might be redundant if the loop handles the last chunk correctly with done=True
    # However, it ensures a "done" signal if words list was empty and the initial check didn't catch it (though it should)
    # or if an error occurred and we want to signal termination.
    # For now, the loop's last chunk should set done=True.
    # Consider if a final explicit done is needed if loop is empty AFTER the initial check.
    # if not words: # This condition might be re-evaluated based on above logic.
    #     final_done_chunk = GenAIChatResponseChunk(text="", done=True)
    #     logger.info(f"Yielding final explicit done chunk: {json.dumps(final_done_chunk.model_dump()) + '\\n'!r}")
    #     yield json.dumps(final_done_chunk.model_dump()) + "\\n"


@router.post("/v1/chat/completions", summary="Chat Completions Endpoint")
async def chat_completions(
    request: GenAIChatRequest
):
    """
    Handles chat completion requests.
    Accepts a list of messages and streams back responses.
    """
    logger.info(f"Received chat completion request. Model: {request.model or 'default'}, Messages: {len(request.messages)}")

    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    if request.stream:
        # logger.info("Streaming response (using generate_simulated_llm_stream)...") 
        logger.info("Streaming response (using generate_minimal_stream_for_debug)...") # MODIFIED
        return StreamingResponse(
            # generate_simulated_llm_stream(request.messages, request.model), # COMMENTED OUT
            generate_minimal_stream_for_debug(), # USING MINIMAL DEBUG STREAM
            media_type="application/x-ndjson" # Newline Delimited JSON
        )
    else:
        # Non-streaming response
        logger.info("Generating non-streaming response...")
        full_response_text = ""
        # This non-streaming path needs to be robust if used.
        # For now, it reuses the async generator, which is fine.
        async for chunk_json_str in generate_simulated_llm_stream(request.messages, request.model):
            try:
                # Assuming chunk_json_str includes the newline, so strip it before parsing
                chunk_dict = json.loads(chunk_json_str.strip())
                if chunk_dict.get("text"):
                    full_response_text += chunk_dict["text"]
                if chunk_dict.get("done"):
                    break
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode chunk for non-streaming: {chunk_json_str!r}, Error: {e}")
                # Decide how to handle, maybe append raw or log and continue
        
        final_chunk = GenAIChatResponseChunk(text=full_response_text, done=True)
        return final_chunk
