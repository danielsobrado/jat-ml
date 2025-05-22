# rag/langgraph_vis/core/builder.py
import logging
from typing import Dict, Any, Type, Callable # Import Callable
import asyncio # Import asyncio
import functools # Import functools

from langgraph.graph import StateGraph, END
from langgraph.graph.graph import CompiledGraph
from pydantic import BaseModel

from ..schemas import GraphDefinition, NodeDefinition, EdgeDefinition, ConditionalEdgesDefinition
from .definitions import STATE_SCHEMAS, NODE_IMPLEMENTATIONS, ROUTER_IMPLEMENTATIONS

logger = logging.getLogger(__name__)

class DynamicGraphBuilderError(Exception):
    pass

class DynamicGraphBuilder:
    def __init__(self, graph_definition_data: Dict[str, Any] | GraphDefinition):
        if isinstance(graph_definition_data, GraphDefinition):
            self.graph_definition = graph_definition_data
        elif isinstance(graph_definition_data, dict):
            try:
                self.graph_definition = GraphDefinition(**graph_definition_data)
            except Exception as e:
                logger.error(f"Failed to parse graph definition dictionary: {e}")
                raise DynamicGraphBuilderError(f"Invalid graph definition data: {e}")
        else:
            raise DynamicGraphBuilderError("graph_definition_data must be a dict or GraphDefinition model.")
        self._validate_definition()
        logger.info(f"DynamicGraphBuilder initialized for graph: '{self.graph_definition.name}' (ID: {self.graph_definition.id})")

    def _validate_definition(self) -> None:
        if not self.graph_definition.nodes:
            raise DynamicGraphBuilderError("Graph definition must contain at least one node.")
        if not self.graph_definition.entry_point_node_id:
            raise DynamicGraphBuilderError("Graph definition must specify an entry_point_node_id.")
        node_ids = {node.id for node in self.graph_definition.nodes}
        if self.graph_definition.entry_point_node_id not in node_ids:
            raise DynamicGraphBuilderError(
                f"Entry point node ID '{self.graph_definition.entry_point_node_id}' not found in defined nodes."
            )
        if self.graph_definition.state_schema_name not in STATE_SCHEMAS:
            raise DynamicGraphBuilderError(
                f"Unknown state_schema_name: '{self.graph_definition.state_schema_name}'. "
                f"Available schemas: {list(STATE_SCHEMAS.keys())}"
            )
        logger.debug("Graph definition basic validation passed.")

    def build(self) -> CompiledGraph:
        logger.info(f"Starting to build graph: '{self.graph_definition.name}'")
        StateClass: Type[BaseModel | dict] = STATE_SCHEMAS[self.graph_definition.state_schema_name] # type: ignore
        workflow = StateGraph(StateClass) # type: ignore
        node_ids_with_outgoing_edges = set()
        for node_def in self.graph_definition.nodes:
            self._add_node_to_workflow(workflow, node_def)
        for edge_def in self.graph_definition.edges:
            workflow.add_edge(edge_def.source, edge_def.target)
            node_ids_with_outgoing_edges.add(edge_def.source)
            logger.debug(f"Added standard edge from '{edge_def.source}' to '{edge_def.target}'.")
        for cond_edges_def in self.graph_definition.conditional_edges:
            self._add_conditional_edges_to_workflow(workflow, cond_edges_def)
            node_ids_with_outgoing_edges.add(cond_edges_def.source_node_id)
        workflow.set_entry_point(self.graph_definition.entry_point_node_id)
        logger.debug(f"Set entry point to '{self.graph_definition.entry_point_node_id}'.")
        all_node_ids = {node.id for node in self.graph_definition.nodes}
        defined_terminal_node_ids = set(self.graph_definition.terminal_node_ids or [])
        for node_id in all_node_ids:
            is_explicitly_terminal = node_id in defined_terminal_node_ids
            has_no_outgoing = node_id not in node_ids_with_outgoing_edges
            if is_explicitly_terminal or has_no_outgoing:
                if node_id != self.graph_definition.entry_point_node_id or \
                   (node_id == self.graph_definition.entry_point_node_id and node_id in node_ids_with_outgoing_edges):
                    if has_no_outgoing and node_id not in defined_terminal_node_ids:
                         logger.debug(f"Node '{node_id}' has no outgoing edges, adding implicit edge to END.")
                         workflow.add_edge(node_id, END)
                    elif is_explicitly_terminal:
                         logger.debug(f"Node '{node_id}' is explicitly terminal, adding edge to END.")
                         workflow.add_edge(node_id, END)
        try:
            compiled_graph = workflow.compile()
            logger.info(f"Graph '{self.graph_definition.name}' built and compiled successfully.")
            return compiled_graph
        except Exception as e:
            logger.error(f"Failed to compile graph '{self.graph_definition.name}': {e}", exc_info=True)
            raise DynamicGraphBuilderError(f"Error compiling graph: {e}")

    def _add_node_to_workflow(self, workflow: StateGraph, node_def: NodeDefinition) -> None:
        node_id = node_def.id
        node_type = node_def.type
        # node_config is the config from the GraphDefinition JSON for this specific node
        node_specific_config = node_def.config if node_def.config else {}

        if node_type not in NODE_IMPLEMENTATIONS:
            raise DynamicGraphBuilderError(
                f"Unknown node type: '{node_type}' for node ID '{node_id}'. "
                f"Available types: {list(NODE_IMPLEMENTATIONS.keys())}"
            )

        original_node_callable: Callable = NODE_IMPLEMENTATIONS[node_type] # type: ignore
        final_node_callable: Callable # type: ignore

        # This is where the global simulation_delay_ms (if any) needs to be merged
        # with the node's specific config.
        # The `execution_config` in `ws_handler.py` is the top-level config for the graph run.
        # LangGraph's `astream_events` `config` parameter is passed to each node's underlying runnable.

        if asyncio.iscoroutinefunction(original_node_callable):
            async def async_wrapper(state: Any, runnable_config: Dict[str, Any] = None) -> Any: # LangGraph passes runnable_config
                # Merge node_specific_config and runnable_config (runtime config)
                # Runtime config (like simulation_delay_ms) should take precedence if there are clashes.
                merged_config = {**node_specific_config, **(runnable_config or {})}
                # The node functions need to be aware of this.
                # For example, `simulation_delay_ms` comes from runnable_config.
                # `message_prefix` comes from node_specific_config.
                logger.debug(f"AsyncWrapper for '{node_id}': node_specific_config={node_specific_config}, runtime_runnable_config={runnable_config}, merged_config={merged_config}")
                return await original_node_callable(state, config=merged_config)
            final_node_callable = async_wrapper
        else:
            def sync_wrapper(state: Any, runnable_config: Dict[str, Any] = None) -> Any:
                merged_config = {**node_specific_config, **(runnable_config or {})}
                logger.debug(f"SyncWrapper for '{node_id}': node_specific_config={node_specific_config}, runtime_runnable_config={runnable_config}, merged_config={merged_config}")
                return original_node_callable(state, config=merged_config)
            final_node_callable = sync_wrapper
        
        workflow.add_node(node_id, final_node_callable) # type: ignore
        logger.debug(f"Added node '{node_id}' of type '{node_type}' with its specific definition config: {node_specific_config}.")

    def _add_conditional_edges_to_workflow(
        self, workflow: StateGraph, cond_edges_def: ConditionalEdgesDefinition
    ) -> None:
        source_node_id = cond_edges_def.source_node_id
        mappings = {mapping.condition_name: mapping.target_node_id for mapping in cond_edges_def.mappings}
        source_node_def = next((n for n in self.graph_definition.nodes if n.id == source_node_id), None)
        if not source_node_def:
            raise DynamicGraphBuilderError(f"Source node '{source_node_id}' for conditional edges not found.")
        router_config = source_node_def.config or {}
        router_function_name = router_config.get("router_function_name")
        if not router_function_name:
            raise DynamicGraphBuilderError(
                f"Node '{source_node_id}' is a source for conditional edges but does not specify "
                f"a 'router_function_name' in its config."
            )
        if router_function_name not in ROUTER_IMPLEMENTATIONS:
            raise DynamicGraphBuilderError(
                f"Unknown router_function_name: '{router_function_name}' for node '{source_node_id}'. "
                f"Available routers: {list(ROUTER_IMPLEMENTATIONS.keys())}"
            )
        
        original_router_callable: Callable = ROUTER_IMPLEMENTATIONS[router_function_name] # type: ignore
        final_router_callable: Callable # type: ignore

        # Routers are typically synchronous as they inspect state, but handle async just in case
        if asyncio.iscoroutinefunction(original_router_callable):
            async def async_router_wrapper(state: Any, runnable_config: Dict[str, Any] = None) -> Any:
                # Merge router_config and runnable_config (runtime config)
                merged_config = {**router_config, **(runnable_config or {})}
                logger.debug(f"AsyncRouterWrapper for '{source_node_id}': router_config={router_config}, runtime_runnable_config={runnable_config}, merged_config={merged_config}")
                return await original_router_callable(state, config=merged_config)
            final_router_callable = async_router_wrapper
        else:
            def sync_router_wrapper(state: Any, runnable_config: Dict[str, Any] = None) -> Any:
                merged_config = {**router_config, **(runnable_config or {})}
                logger.debug(f"SyncRouterWrapper for '{source_node_id}': router_config={router_config}, runtime_runnable_config={runnable_config}, merged_config={merged_config}")
                return original_router_callable(state, config=merged_config)
            final_router_callable = sync_router_wrapper
            
        workflow.add_conditional_edges(source_node_id, final_router_callable, mappings) # type: ignore
        logger.debug(f"Added conditional edges from '{source_node_id}' using router '{router_function_name}' with mappings: {mappings}.")
