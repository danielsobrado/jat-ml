# rag/langgraph_vis/core/definitions.py
import logging
from typing import TypedDict, Annotated, List, Optional, Dict, Any
import operator
import asyncio 
from datetime import datetime # Ensure datetime is imported

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from langgraph.graph import StateGraph, END
from langgraph.graph.graph import CompiledGraph

# Import schemas needed for defining the structure in metadata
from ..schemas import NodeDefinition as SchemaNodeDefinition, EdgeDefinition as SchemaEdgeDefinition, ConditionalEdgesDefinition as SchemaConditionalEdgesDefinition, ConditionalEdgeMapping as SchemaConditionalEdgeMapping, NodeUIPosition

logger = logging.getLogger(__name__)

# --- 1. Pydantic State Definitions ---
class BasicAgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next_node: Optional[str] = None
    last_tool_call: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class DocumentProcessingState(BaseModel):
    original_document: str = Field(..., description="The initial document text.")
    processed_document: Optional[str] = Field(None, description="Document after some processing step.")
    summary: Optional[str] = Field(None, description="Summary of the document.")
    keywords: List[str] = Field(default_factory=list, description="Extracted keywords.")
    confidence_score: Optional[float] = Field(None, description="A score related to some processing step.")
    is_processed_successfully: bool = False
    error_info: Optional[str] = None
    class Config:
        extra = "allow"

# --- Helper function for simulation delay ---
async def apply_simulation_delay(config: Optional[Dict[str, Any]], default_delay_s: float = 0):
    """Applies a delay if simulation_delay_ms is found in config."""
    if config and "simulation_delay_ms" in config:
        delay_ms = config.get("simulation_delay_ms", 0)
        if isinstance(delay_ms, (int, float)) and delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)
            logger.debug(f"Applied simulation delay: {delay_ms}ms")
            return
    # Fallback to any hardcoded default delay if present (though we're removing them)
    elif default_delay_s > 0:
        await asyncio.sleep(default_delay_s)

# --- 2. Example Node Functions/Runnables ---
async def entry_point_node(state: BasicAgentState, config: Optional[Dict[str, Any]] = None) -> BasicAgentState:
    logger.info(f"Executing entry_point_node with config: {config}")
    await apply_simulation_delay(config) 
    if not state.get("messages"): 
        state["messages"] = []
    state["messages"].append(HumanMessage(content="Workflow started by entry_point_node"))
    state["next_node"] = "agent_node" 
    return state

async def simple_message_modifier_node(state: BasicAgentState, config: Optional[Dict[str, Any]] = None) -> BasicAgentState:
    node_id_for_log = config.get("node_id_for_log", "simple_message_modifier_node") if config else "simple_message_modifier_node"
    logger.info(f"Executing {node_id_for_log} with config: {config}")
    await apply_simulation_delay(config)
    prefix = config.get("message_prefix", "Modified: ") if config else "Modified: "
    if state.get("messages") and state["messages"]: # Check if messages list exists and is not empty
        last_message_content = state["messages"][-1].content
        state["messages"].append(AIMessage(content=f"{prefix}{last_message_content}"))
    else:
        if not state.get("messages"): state["messages"] = [] # Ensure messages list exists
        state["messages"].append(AIMessage(content=f"{prefix}No previous message."))
    return state

async def simulated_llm_node(state: DocumentProcessingState, config: Optional[Dict[str, Any]] = None) -> DocumentProcessingState:
    node_id_for_log = config.get("node_id_for_log", "simulated_llm_node") if config else "simulated_llm_node"
    logger.info(f"Executing {node_id_for_log} with config: {config}")
    await apply_simulation_delay(config) 
    action = config.get("action", "summarize") if config else "summarize"
    doc_to_process = state.processed_document or state.original_document
    # No default hardcoded delay, use simulation_delay_ms instead
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

async def simulated_tool_node(state: BasicAgentState, config: Optional[Dict[str, Any]] = None) -> BasicAgentState:
    tool_name = config.get("tool_name", "generic_tool") if config else "generic_tool"
    node_id_for_log = config.get("node_id_for_log", f"simulated_tool_node:{tool_name}") if config else f"simulated_tool_node:{tool_name}"
    logger.info(f"Executing {node_id_for_log} with config: {config}")
    await apply_simulation_delay(config) 
    tool_input_key = config.get("input_key", "tool_input") if config else "tool_input" 
    tool_output_key = config.get("output_key", "tool_output") if config else "tool_output"
    tool_input_value = "No specific input provided"
    if state.get("messages") and state["messages"] and tool_input_key == "last_message_content": # Check messages existence
        tool_input_value = state["messages"][-1].content
    elif state.get(tool_input_key): # type: ignore
        tool_input_value = state[tool_input_key] # type: ignore
    logger.info(f"Executing simulated_tool_node: {tool_name} with input: '{tool_input_value}'")
    # No default hardcoded delay, use simulation_delay_ms instead
    tool_result = f"Result from {tool_name} for input '{tool_input_value}'"
    if not state.get("messages"): state["messages"] = [] # Ensure messages list exists
    state["messages"].append(ToolMessage(content=tool_result, tool_call_id=tool_name)) # type: ignore
    state[tool_output_key] = tool_result # type: ignore
    state["last_tool_call"] = {"name": tool_name, "input": tool_input_value, "output": tool_result}
    return state

def route_based_on_llm_output(state: DocumentProcessingState, config: Optional[Dict[str, Any]] = None) -> str:
    logger.info(f"Executing router: route_based_on_llm_output. Confidence: {state.confidence_score}")
    decision_threshold = config.get("decision_threshold", 0.8) if config else 0.8
    if state.error_info: return "error_handler_path" 
    if state.confidence_score is not None and state.confidence_score >= decision_threshold: return "high_confidence_path"
    else: return "low_confidence_path"

def agent_router(state: BasicAgentState) -> str:
    if state.get("next_node"):
        next_val = state.pop("next_node") 
        logger.info(f"Agent router: Explicitly routing to '{next_val}'")
        return str(next_val)
    if state.get("messages") and state["messages"]: # Check messages existence
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and not state.get("last_tool_call"):
            logger.info("Agent router: AIMessage, no tool call, routing to end.")
            return END
        elif isinstance(last_message, HumanMessage) or isinstance(last_message, ToolMessage):
            logger.info("Agent router: Human or Tool message, routing to agent_node.")
            return "agent_node"
    logger.info("Agent router: Defaulting to end.")
    return END 

# --- 3. Example Static Graph Construction ---
def create_example_document_workflow() -> CompiledGraph:
    workflow = StateGraph(DocumentProcessingState)

    async def _doc_processor_node(state: DocumentProcessingState, invoke_config: Optional[Dict[str, Any]]=None):
        node_specific_config = {"action": "summarize", "router_function_name": "document_confidence_router", "node_id_for_log": "doc_processor"}
        final_config = {**node_specific_config, **(invoke_config or {})}
        return await simulated_llm_node(state, config=final_config)

    async def _final_summary_node(state: DocumentProcessingState, invoke_config: Optional[Dict[str, Any]]=None):
        node_specific_config = {"action": "extract_keywords", "num_keywords": 5, "node_id_for_log": "final_summary_node"}
        final_config = {**node_specific_config, **(invoke_config or {})}
        return await simulated_llm_node(state, config=final_config)

    async def _error_handling_node_doc_workflow(state: DocumentProcessingState, invoke_config: Optional[Dict[str, Any]]=None):
        node_id_for_log = "error_handling_node"
        error_prefix = "StaticError: "
        logger.info(f"Executing {node_id_for_log} with effective config including invoke_config: {invoke_config}")
        await apply_simulation_delay(invoke_config)
        state.error_info = (state.error_info or "Error encountered during processing") + \
                           f" - {error_prefix}Document processing failed or led to error path."
        state.is_processed_successfully = False
        logger.warning(f"{node_id_for_log}: Document processing marked as failed. Error info: {state.error_info}")
        return state

    workflow.add_node("doc_processor", _doc_processor_node)
    workflow.add_node("final_summary_node", _final_summary_node)
    workflow.add_node("error_handling_node", _error_handling_node_doc_workflow)

    workflow.set_entry_point("doc_processor")

    # Define the router function explicitly for clarity and to potentially resolve type issues
    def _doc_processor_router(state: DocumentProcessingState) -> str:
        # Configuration for this specific routing instance
        router_config = {"decision_threshold": 0.7}
        return route_based_on_llm_output(state, config=router_config)

    workflow.add_conditional_edges(
        "doc_processor",
        _doc_processor_router,  # Use the explicitly defined router function
        {"high_confidence_path": "final_summary_node", "low_confidence_path": "error_handling_node", "error_handler_path": "error_handling_node"}
    )
    workflow.add_edge("error_handling_node", END)
    workflow.add_edge("final_summary_node", END)
    compiled_graph = workflow.compile()
    setattr(compiled_graph, 'compiled_at', datetime.utcnow())
    logger.info("Example document workflow compiled successfully.")
    return compiled_graph

def create_basic_agent_workflow() -> CompiledGraph:
    graph = StateGraph(BasicAgentState)

    async def _entry_node(state: BasicAgentState, invoke_config: Optional[Dict[str, Any]]=None):
        node_specific_config = {"node_id_for_log": "entry_node"} # Original lambda config was {}
        final_config = {**node_specific_config, **(invoke_config or {})}
        return await entry_point_node(state, config=final_config)

    async def _agent_node(state: BasicAgentState, invoke_config: Optional[Dict[str, Any]]=None):
        node_specific_config = {"message_prefix": "AgentMod: ", "node_id_for_log": "agent_node"}
        final_config = {**node_specific_config, **(invoke_config or {})}
        return await simple_message_modifier_node(state, config=final_config)

    async def _tool_node(state: BasicAgentState, invoke_config: Optional[Dict[str, Any]]=None):
        node_specific_config = {"tool_name": "static_tool", "node_id_for_log": "tool_node"}
        final_config = {**node_specific_config, **(invoke_config or {})}
        return await simulated_tool_node(state, config=final_config)

    graph.add_node("entry_node", _entry_node)
    graph.add_node("agent_node", _agent_node)
    graph.add_node("tool_node", _tool_node)

    graph.set_entry_point("entry_node")
    graph.add_conditional_edges("entry_node", agent_router, {"agent_node": "agent_node", "tool_node": "tool_node", END: END})
    graph.add_conditional_edges("agent_node", agent_router, {"tool_node": "tool_node", END: END})
    graph.add_edge("tool_node", "agent_node")
    compiled_graph = graph.compile()
    setattr(compiled_graph, 'compiled_at', datetime.utcnow())
    logger.info("Basic agent workflow compiled successfully.")
    return compiled_graph

# --- Registries ---
NODE_IMPLEMENTATIONS: Dict[str, callable] = { # type: ignore[type-arg]
    "entry_point": entry_point_node, "simple_modifier": simple_message_modifier_node,
    "llm_node": simulated_llm_node, "tool_node": simulated_tool_node,
}
ROUTER_IMPLEMENTATIONS: Dict[str, callable] = { # type: ignore[type-arg]
    "document_confidence_router": route_based_on_llm_output, "basic_agent_router": agent_router,
}
STATE_SCHEMAS: Dict[str, type[TypedDict] | type[BaseModel]] = { # type: ignore[type-arg]
    "BasicAgentState": BasicAgentState, "DocumentProcessingState": DocumentProcessingState,
}

# --- Enhanced STATIC_GRAPHS_METADATA ---
STATIC_GRAPHS_METADATA: Dict[str, Dict[str, Any]] = {
    "example_document_workflow": {
        "compiled_graph": create_example_document_workflow(),
        "state_schema_name": "DocumentProcessingState",
        "description": "A statically defined workflow for processing documents and generating summaries or keywords based on confidence.",
        "entry_point_node_id": "doc_processor",
        "nodes": [
            SchemaNodeDefinition(id="doc_processor", type="llm_node", config={"action": "summarize", "router_function_name": "document_confidence_router"}, ui_position=NodeUIPosition(x=100, y=200)),
            SchemaNodeDefinition(id="final_summary_node", type="llm_node", config={"action": "extract_keywords", "num_keywords": 5}, ui_position=NodeUIPosition(x=400, y=100)),
            SchemaNodeDefinition(id="error_handling_node", type="simple_modifier", config={"message_prefix": "StaticError: "}, ui_position=NodeUIPosition(x=400, y=300)),
        ],
        "edges": [], # No standard edges in this example, only conditional
        "conditional_edges": [
            SchemaConditionalEdgesDefinition(
                source_node_id="doc_processor",
                mappings=[
                    SchemaConditionalEdgeMapping(condition_name="high_confidence_path", target_node_id="final_summary_node"),
                    SchemaConditionalEdgeMapping(condition_name="low_confidence_path", target_node_id="error_handling_node"),
                    SchemaConditionalEdgeMapping(condition_name="error_handler_path", target_node_id="error_handling_node"),
                ]
            )
        ],
        "terminal_node_ids": ["final_summary_node", "error_handling_node"],
    },
    "basic_agent_workflow": {
        "compiled_graph": create_basic_agent_workflow(),
        "state_schema_name": "BasicAgentState",
        "description": "A basic agent that can use a simulated tool and modify messages.",
        "entry_point_node_id": "entry_node",
        "nodes": [
            SchemaNodeDefinition(id="entry_node", type="entry_point", config={}, ui_position=NodeUIPosition(x=100, y=100)),
            SchemaNodeDefinition(id="agent_node", type="simple_modifier", config={"message_prefix": "AgentMod: "}, ui_position=NodeUIPosition(x=300, y=100)),
            SchemaNodeDefinition(id="tool_node", type="tool_node", config={"tool_name": "static_tool"}, ui_position=NodeUIPosition(x=300, y=250)),
        ],
        "edges": [ # This graph has standard edges
            SchemaEdgeDefinition(id="e_tool_to_agent", source="tool_node", target="agent_node", label="Tool Output")
        ],
        "conditional_edges": [
            SchemaConditionalEdgesDefinition(
                source_node_id="entry_node",
                mappings=[
                    SchemaConditionalEdgeMapping(condition_name="agent_node", target_node_id="agent_node"),
                    SchemaConditionalEdgeMapping(condition_name="tool_node", target_node_id="tool_node"),
                    SchemaConditionalEdgeMapping(condition_name=END, target_node_id=END), # Target can be END
                ]
            ),
            SchemaConditionalEdgesDefinition(
                source_node_id="agent_node",
                mappings=[
                    SchemaConditionalEdgeMapping(condition_name="tool_node", target_node_id="tool_node"),
                    SchemaConditionalEdgeMapping(condition_name=END, target_node_id=END),
                ]
            ),
        ],
        "terminal_node_ids": [], # END is handled by conditional edges directly
    },
}

STATIC_GRAPHS: Dict[str, CompiledGraph] = {
    name: data["compiled_graph"] for name, data in STATIC_GRAPHS_METADATA.items()
}