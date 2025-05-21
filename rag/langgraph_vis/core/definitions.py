# rag/langgraph_vis/core/definitions.py
import logging
from typing import TypedDict, Annotated, List, Optional, Dict, Any
import operator
import asyncio # For async node examples

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from langgraph.graph import StateGraph, END
from langgraph.graph.graph import CompiledGraph
# from langgraph.checkpoint import BaseCheckpointSaver # If using checkpoints for static graphs

logger = logging.getLogger(__name__)

# --- 1. Pydantic State Definitions for LangGraphs ---
# These can be registered and then referenced by 'state_schema_name' in JSON graph definitions.

class BasicAgentState(TypedDict):
    """
    A simple state for an agent that processes messages and can make decisions.
    """
    messages: Annotated[List[BaseMessage], operator.add]
    next_node: Optional[str] = None # For explicit routing by a node
    last_tool_call: Optional[Dict[str, Any]] = None # Example of storing tool call info
    error_message: Optional[str] = None # To store errors within the graph flow

class DocumentProcessingState(BaseModel):
    """
    A Pydantic BaseModel state for a document processing workflow.
    Using BaseModel allows for more complex validation and features if needed.
    """
    original_document: str = Field(..., description="The initial document text.")
    processed_document: Optional[str] = Field(None, description="Document after some processing step.")
    summary: Optional[str] = Field(None, description="Summary of the document.")
    keywords: List[str] = Field(default_factory=list, description="Extracted keywords.")
    confidence_score: Optional[float] = Field(None, description="A score related to some processing step.")
    is_processed_successfully: bool = False
    error_info: Optional[str] = None

    # Config for Pydantic model, e.g., to allow extra fields if necessary for LangGraph
    class Config:
        extra = "allow" # LangGraph might add its own internal state fields

# --- 2. Example Node Functions/Runnables ---
# These are the building blocks. The dynamic builder (`builder.py`) will map
# `node.type` from graph definition JSON to these (or similar) Python callables.
# Each node function should accept the graph's state as its first argument and
# return a dictionary (or Pydantic model instance) representing the changes to the state.

# Example Simple Nodes
async def entry_point_node(state: BasicAgentState) -> BasicAgentState:
    logger.info("Executing entry_point_node")
    # This node might initialize something or simply pass through.
    # For BasicAgentState, it primarily receives the initial input via 'messages'.
    if not state.get("messages"): # Ensure messages list exists
        state["messages"] = []
    state["messages"].append(HumanMessage(content="Workflow started by entry_point_node"))
    state["next_node"] = "agent_node" # Example of directing to the next node
    return state

async def simple_message_modifier_node(state: BasicAgentState, config: Optional[Dict[str, Any]] = None) -> BasicAgentState:
    logger.info(f"Executing simple_message_modifier_node with config: {config}")
    prefix = config.get("message_prefix", "Modified: ") if config else "Modified: "
    if state["messages"]:
        last_message_content = state["messages"][-1].content
        state["messages"].append(AIMessage(content=f"{prefix}{last_message_content}"))
    else:
        state["messages"].append(AIMessage(content=f"{prefix}No previous message."))
    return state

# Example "LLM" Node (Simulated)
async def simulated_llm_node(state: DocumentProcessingState, config: Optional[Dict[str, Any]] = None) -> DocumentProcessingState:
    logger.info(f"Executing simulated_llm_node with config: {config}")
    action = config.get("action", "summarize") if config else "summarize"
    doc_to_process = state.processed_document or state.original_document

    await asyncio.sleep(0.1) # Simulate network latency

    if action == "summarize":
        state.summary = f"Simulated summary of: {doc_to_process[:50]}..."
        state.confidence_score = 0.85
    elif action == "extract_keywords":
        state.keywords = [f"sim_kw_{i+1}" for i in range(config.get("num_keywords", 3))] # type: ignore
        state.confidence_score = 0.90
    else:
        state.error_info = f"Unknown LLM action: {action}"
        state.is_processed_successfully = False
        return state

    state.is_processed_successfully = True
    return state

# Example "Tool" Node (Simulated)
async def simulated_tool_node(state: BasicAgentState, config: Optional[Dict[str, Any]] = None) -> BasicAgentState:
    tool_name = config.get("tool_name", "generic_tool") if config else "generic_tool"
    tool_input_key = config.get("input_key", "tool_input") if config else "tool_input" # Key in state for tool input
    tool_output_key = config.get("output_key", "tool_output") if config else "tool_output" # Key in state for tool output

    # Assuming the tool input might be the content of the last message or a specific field
    tool_input_value = "No specific input provided"
    if state["messages"] and tool_input_key == "last_message_content":
        tool_input_value = state["messages"][-1].content
    elif state.get(tool_input_key): # type: ignore
        tool_input_value = state[tool_input_key] # type: ignore

    logger.info(f"Executing simulated_tool_node: {tool_name} with input: '{tool_input_value}'")
    await asyncio.sleep(0.05) # Simulate tool execution time

    # Simulate tool output
    tool_result = f"Result from {tool_name} for input '{tool_input_value}'"
    state["messages"].append(ToolMessage(content=tool_result, tool_call_id=tool_name)) # type: ignore
    state[tool_output_key] = tool_result # type: ignore
    state["last_tool_call"] = {"name": tool_name, "input": tool_input_value, "output": tool_result}

    return state

# Example Router Function (for conditional edges)
def route_based_on_llm_output(state: DocumentProcessingState, config: Optional[Dict[str, Any]] = None) -> str:
    """
    A simple router that directs flow based on the confidence score.
    The string returned by this function must match one of the keys in the
    conditional_edges mapping in the graph definition (or JSON).
    """
    logger.info(f"Executing router: route_based_on_llm_output. Confidence: {state.confidence_score}")
    decision_threshold = config.get("decision_threshold", 0.8) if config else 0.8

    if state.error_info:
        return "error_handler_path" # Corresponds to a key in conditional_edges mappings
    if state.confidence_score is not None and state.confidence_score >= decision_threshold:
        return "high_confidence_path"
    else:
        return "low_confidence_path"

def agent_router(state: BasicAgentState) -> str:
    """
    Router for the BasicAgentState.
    Checks the 'next_node' field if set by a previous node, or makes a decision.
    """
    if state.get("next_node"):
        next_val = state.pop("next_node") # Consume the explicit routing
        logger.info(f"Agent router: Explicitly routing to '{next_val}'")
        return str(next_val) # Ensure it's a string

    # Fallback: if last message was an AIMessage and no tool call, consider ending.
    # Otherwise, if last message was a HumanMessage or ToolMessage, go to agent.
    # This is a very simplified agent logic.
    if state["messages"]:
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and not state.get("last_tool_call"):
            logger.info("Agent router: AIMessage, no tool call, routing to end.")
            return END
        elif isinstance(last_message, HumanMessage) or isinstance(last_message, ToolMessage):
            logger.info("Agent router: Human or Tool message, routing to agent_node.")
            return "agent_node" # Loop back to agent or process more

    logger.info("Agent router: Defaulting to end.")
    return END # Default case or if no messages


# --- 3. Example Static Graph Construction ---

def create_example_document_workflow() -> CompiledGraph:
    """
    Creates and compiles an example LangGraph for document processing.
    This demonstrates how to build a graph programmatically.
    The dynamic builder will do something similar but based on JSON definitions.
    """
    workflow = StateGraph(DocumentProcessingState)

    # Add nodes
    # The node names here ('doc_processor', 'doc_router') are what you'd use in JSON graph definitions.
    workflow.add_node("doc_processor", simulated_llm_node) # type: ignore
    workflow.add_node("final_summary_node", simulated_llm_node) # type: ignore
    workflow.add_node("error_handling_node", simple_message_modifier_node) # type: ignore

    # Set entry point
    workflow.set_entry_point("doc_processor")

    # Add conditional edges from the router
    # The 'doc_router' node itself would be added if it performed state modification
    # Here, route_based_on_llm_output is used directly as the conditional router logic for 'doc_processor's output.
    # If you wanted a separate 'doc_router' node, that node's function would return the condition string.
    workflow.add_conditional_edges(
        "doc_processor", # Source node
        route_based_on_llm_output, # The router function
        { # Mapping of: condition_string_returned_by_router -> target_node_name
            "high_confidence_path": "final_summary_node",
            "low_confidence_path": "error_handling_node", # Or could go to another processing step
            "error_handler_path": "error_handling_node"
        }
    )

    # Add regular edges
    workflow.add_edge("error_handling_node", END)
    workflow.add_edge("final_summary_node", END) # Both paths eventually end

    # Compile the graph
    compiled_graph = workflow.compile()
    logger.info("Example document workflow compiled successfully.")
    return compiled_graph

def create_basic_agent_workflow() -> CompiledGraph:
    """Creates a basic agent loop."""
    graph = StateGraph(BasicAgentState)

    graph.add_node("entry_node", entry_point_node) # type: ignore
    graph.add_node("agent_node", simple_message_modifier_node) # Example: agent just modifies message
    graph.add_node("tool_node", simulated_tool_node) # type: ignore

    graph.set_entry_point("entry_node")

    # The agent_router function will decide where to go from 'entry_node' and 'agent_node'
    graph.add_conditional_edges(
        "entry_node",
        agent_router,
        {"agent_node": "agent_node", "tool_node": "tool_node", END: END}
    )
    graph.add_conditional_edges(
        "agent_node",
        agent_router,
        {"tool_node": "tool_node", END: END} # From agent, can call tool or end
    )
    # After tool execution, always go back to the agent_node to process tool output
    graph.add_edge("tool_node", "agent_node")

    compiled_graph = graph.compile()
    logger.info("Basic agent workflow compiled successfully.")
    return compiled_graph


# --- Registry of Node Types and State Schemas (for dynamic builder) ---
# The dynamic builder (`builder.py`) will use these registries to map strings
# from JSON graph definitions to actual Python callables and Pydantic models.

NODE_IMPLEMENTATIONS: Dict[str, callable] = { # type: ignore[type-arg]
    "entry_point": entry_point_node,
    "simple_modifier": simple_message_modifier_node,
    "llm_node": simulated_llm_node,
    "tool_node": simulated_tool_node,
    # Note: Router nodes are often implicitly handled by `add_conditional_edges`
    # if the source node's function itself or a separate router function provides the condition.
    # If a router node *modifies state before routing*, you'd register its function here too.
    # "stateful_router_node": some_state_modifying_router_function,
}

ROUTER_IMPLEMENTATIONS: Dict[str, callable] = { # type: ignore[type-arg]
    "document_confidence_router": route_based_on_llm_output,
    "basic_agent_router": agent_router,
}

# For State Schemas, we register the classes themselves.
# The builder will instantiate them.
STATE_SCHEMAS: Dict[str, type[TypedDict] | type[BaseModel]] = { # type: ignore[type-arg]
    "BasicAgentState": BasicAgentState,
    "DocumentProcessingState": DocumentProcessingState,
}

# You might also have a registry for pre-compiled static graphs if you want to expose them
# via the API by name, e.g., for execution without needing a full JSON definition.
STATIC_GRAPHS: Dict[str, CompiledGraph] = {
    "example_document_workflow": create_example_document_workflow(),
    "basic_agent_workflow": create_basic_agent_workflow(),
}

if __name__ == "__main__":
    # Example of running a static graph (for testing this file)
    doc_workflow = STATIC_GRAPHS["example_document_workflow"]
    initial_state_doc = DocumentProcessingState(original_document="This is a test document about AI and LangGraph.")
    
    print("\n--- Running Document Workflow ---")
    # For async graphs, you'd typically use `async for ... in doc_workflow.astream(initial_state_doc):`
    # Here, we'll just invoke it for simplicity, assuming nodes are async but top-level call is blocking.
    # This requires `invoke` to handle async nodes internally or nodes to be adaptable.
    # LangGraph's default invoke can handle async nodes if run in an async context.
    # To run this example directly:
    async def run_doc_workflow():
        final_state_doc = await doc_workflow.ainvoke(initial_state_doc, {"recursion_limit": 10})
        print("Final Document Workflow State:")
        print(final_state_doc)

    # asyncio.run(run_doc_workflow()) # Uncomment to test

    agent_workflow = STATIC_GRAPHS["basic_agent_workflow"]
    initial_state_agent = BasicAgentState(messages=[HumanMessage(content="Hello agent!")])

    print("\n--- Running Basic Agent Workflow ---")
    async def run_agent_workflow():
        final_state_agent = await agent_workflow.ainvoke(initial_state_agent, {"recursion_limit": 10})
        print("Final Agent Workflow State:")
        print(final_state_agent)

    # asyncio.run(run_agent_workflow()) # Uncomment to test