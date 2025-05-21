# rag/langgraph_vis/core/builder.py
import logging
from typing import Dict, Any, Type

from langgraph.graph import StateGraph, END
from langgraph.graph.graph import CompiledGraph
from pydantic import BaseModel

# Assuming schemas.py is in the parent directory or accessible via adjusted import path
from ..schemas import GraphDefinition, NodeDefinition, EdgeDefinition, ConditionalEdgesDefinition
# Assuming definitions.py is in the same directory or accessible
from .definitions import STATE_SCHEMAS, NODE_IMPLEMENTATIONS, ROUTER_IMPLEMENTATIONS

logger = logging.getLogger(__name__)

class DynamicGraphBuilderError(Exception):
    """Custom exception for errors during dynamic graph building."""
    pass

class DynamicGraphBuilder:
    """
    Builds a LangGraph CompiledGraph from a GraphDefinition Pydantic model.
    """

    def __init__(self, graph_definition_data: Dict[str, Any] | GraphDefinition):
        """
        Initializes the builder with graph definition data.

        Args:
            graph_definition_data: Either a dictionary or a GraphDefinition Pydantic model.
        """
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
        """
        Performs basic validation of the graph definition.
        """
        if not self.graph_definition.nodes:
            raise DynamicGraphBuilderError("Graph definition must contain at least one node.")
        if not self.graph_definition.entry_point_node_id:
            raise DynamicGraphBuilderError("Graph definition must specify an entry_point_node_id.")

        node_ids = {node.id for node in self.graph_definition.nodes}
        if self.graph_definition.entry_point_node_id not in node_ids:
            raise DynamicGraphBuilderError(
                f"Entry point node ID '{self.graph_definition.entry_point_node_id}' not found in defined nodes."
            )

        # Validate state schema
        if self.graph_definition.state_schema_name not in STATE_SCHEMAS:
            raise DynamicGraphBuilderError(
                f"Unknown state_schema_name: '{self.graph_definition.state_schema_name}'. "
                f"Available schemas: {list(STATE_SCHEMAS.keys())}"
            )
        logger.debug("Graph definition basic validation passed.")


    def build(self) -> CompiledGraph:
        """
        Constructs and compiles the LangGraph based on the definition.

        Returns:
            A CompiledGraph instance.
        """
        logger.info(f"Starting to build graph: '{self.graph_definition.name}'")

        StateClass: Type[BaseModel | dict] = STATE_SCHEMAS[self.graph_definition.state_schema_name] # type: ignore
        workflow = StateGraph(StateClass) # type: ignore

        # 1. Add all nodes
        node_ids_with_outgoing_edges = set()
        for node_def in self.graph_definition.nodes:
            self._add_node_to_workflow(workflow, node_def)

        # 2. Add standard edges
        for edge_def in self.graph_definition.edges:
            workflow.add_edge(edge_def.source, edge_def.target)
            node_ids_with_outgoing_edges.add(edge_def.source)
            logger.debug(f"Added standard edge from '{edge_def.source}' to '{edge_def.target}'.")

        # 3. Add conditional edges
        for cond_edges_def in self.graph_definition.conditional_edges:
            self._add_conditional_edges_to_workflow(workflow, cond_edges_def)
            node_ids_with_outgoing_edges.add(cond_edges_def.source_node_id)

        # 4. Set the entry point
        workflow.set_entry_point(self.graph_definition.entry_point_node_id)
        logger.debug(f"Set entry point to '{self.graph_definition.entry_point_node_id}'.")

        # 5. Handle terminal nodes (nodes that should implicitly go to END)
        # This includes nodes explicitly listed as terminal
        # AND nodes that have no outgoing edges defined in edges or conditional_edges.
        all_node_ids = {node.id for node in self.graph_definition.nodes}
        defined_terminal_node_ids = set(self.graph_definition.terminal_node_ids or [])

        for node_id in all_node_ids:
            is_explicitly_terminal = node_id in defined_terminal_node_ids
            has_no_outgoing = node_id not in node_ids_with_outgoing_edges

            if is_explicitly_terminal or has_no_outgoing:
                # Avoid adding END edge if it's the entry point and also terminal with no other path
                # (LangGraph handles this, but good to be mindful)
                # Also, ensure it's not a source of conditional edges already (covered by node_ids_with_outgoing_edges)
                if node_id != self.graph_definition.entry_point_node_id or \
                   (node_id == self.graph_definition.entry_point_node_id and node_id in node_ids_with_outgoing_edges):
                    # Add edge to END only if it's not already handled or if it's an intermediate node becoming terminal
                    if has_no_outgoing and node_id not in defined_terminal_node_ids: # Implicitly terminal
                         logger.debug(f"Node '{node_id}' has no outgoing edges, adding implicit edge to END.")
                         workflow.add_edge(node_id, END)
                    elif is_explicitly_terminal: # Explicitly terminal
                         logger.debug(f"Node '{node_id}' is explicitly terminal, adding edge to END.")
                         workflow.add_edge(node_id, END)


        # 6. Compile the graph
        try:
            compiled_graph = workflow.compile()
            logger.info(f"Graph '{self.graph_definition.name}' built and compiled successfully.")
            return compiled_graph
        except Exception as e:
            logger.error(f"Failed to compile graph '{self.graph_definition.name}': {e}", exc_info=True)
            raise DynamicGraphBuilderError(f"Error compiling graph: {e}")


    def _add_node_to_workflow(self, workflow: StateGraph, node_def: NodeDefinition) -> None:
        """Helper to add a single node to the workflow."""
        node_id = node_def.id
        node_type = node_def.type
        node_config = node_def.config if node_def.config else {}

        if node_type not in NODE_IMPLEMENTATIONS:
            raise DynamicGraphBuilderError(
                f"Unknown node type: '{node_type}' for node ID '{node_id}'. "
                f"Available types: {list(NODE_IMPLEMENTATIONS.keys())}"
            )

        node_callable = NODE_IMPLEMENTATIONS[node_type]

        # Pass config to the node callable.
        # The node function itself needs to be designed to accept a 'config' argument if it needs one.
        # We can use a lambda to pass the config if the node function expects it.
        # A more robust way is for node functions to have a signature like `my_node(state, config=None)`
        # For simplicity, assuming node callables can handle a 'config' kwarg if provided.
        # A common pattern:
        # def my_node_function(state: State, config: Optional[Dict[str, Any]] = None): ...
        # If the node function does not accept 'config', this will cause an error.
        # One way to handle this is to inspect the callable's signature, or ensure all node callables
        # in NODE_IMPLEMENTATIONS accept `config: Optional[Dict[str, Any]] = None`.
        # For now, let's assume they do, as per our `definitions.py` examples.

        # We bind the config to the node_callable here
        configured_node_callable = lambda state: node_callable(state, config=node_config) # type: ignore

        workflow.add_node(node_id, configured_node_callable) # type: ignore
        logger.debug(f"Added node '{node_id}' of type '{node_type}' with config: {node_config}.")


    def _add_conditional_edges_to_workflow(
        self, workflow: StateGraph, cond_edges_def: ConditionalEdgesDefinition
    ) -> None:
        """Helper to add conditional edges for a source node."""
        source_node_id = cond_edges_def.source_node_id
        mappings = {mapping.condition_name: mapping.target_node_id for mapping in cond_edges_def.mappings}

        # Determine the router function.
        # It could be a named router from ROUTER_IMPLEMENTATIONS, or the source node itself might return the condition.
        # The GraphDefinition schema would need a field to specify this, e.g., `router_function_name`.
        # For now, let's assume a `config` field within the source node's definition can specify a router.
        source_node_def = next((n for n in self.graph_definition.nodes if n.id == source_node_id), None)
        if not source_node_def:
            raise DynamicGraphBuilderError(f"Source node '{source_node_id}' for conditional edges not found.")

        router_config = source_node_def.config or {}
        router_function_name = router_config.get("router_function_name") # e.g. "document_confidence_router"

        if router_function_name:
            if router_function_name not in ROUTER_IMPLEMENTATIONS:
                raise DynamicGraphBuilderError(
                    f"Unknown router_function_name: '{router_function_name}' for node '{source_node_id}'. "
                    f"Available routers: {list(ROUTER_IMPLEMENTATIONS.keys())}"
                )
            router_callable = ROUTER_IMPLEMENTATIONS[router_function_name]
            # Pass the source node's config to the router callable, if it accepts it
            # Similar to node callables, router functions should be designed to accept `config`
            configured_router_callable = lambda state: router_callable(state, config=router_config) # type: ignore
        else:
            # If no router_function_name is specified in node config, assume the source_node_id's
            # own output (after its execution) is the condition string to be used for mapping.
            # LangGraph's `add_conditional_edges` expects the callable to return the condition string.
            # The source node's *function output* (the dict it returns) should contain a key whose
            # value is the condition string.
            # For simplicity, we often use a dedicated router function that just inspects state.
            # If the node itself decides, it needs to update state with the condition string.
            # Let's assume if no router_function_name, the node's output dict has a key, e.g. "next_condition"
            # This part requires a clear convention in your graph definitions.
            # For our `definitions.py` examples, router functions are separate.
            # So, we will require `router_function_name` to be specified in the source node's config.
            raise DynamicGraphBuilderError(
                f"Node '{source_node_id}' is a source for conditional edges but does not specify "
                f"a 'router_function_name' in its config. This builder requires an explicit router function."
            )

        workflow.add_conditional_edges(source_node_id, configured_router_callable, mappings) # type: ignore
        logger.debug(f"Added conditional edges from '{source_node_id}' using router '{router_function_name}' with mappings: {mappings}.")


# Example Usage (for testing this file, assuming schemas.py and definitions.py are importable)
if __name__ == "__main__":
    # This example assumes you have JSON data or a dict representing a GraphDefinition
    example_graph_def_data = {
        "id": "test_dynamic_graph_001",
        "name": "Test Dynamic Document Workflow",
        "description": "A dynamically built version of the document workflow.",
        "state_schema_name": "DocumentProcessingState",
        "nodes": [
            {
                "id": "doc_processor_dyn",
                "type": "llm_node",
                "config": {"action": "summarize", "router_function_name": "document_confidence_router"}, # Router defined here
                "ui_position": {"x": 100, "y": 100}
            },
            {
                "id": "final_summary_node_dyn",
                "type": "llm_node",
                "config": {"action": "extract_keywords", "num_keywords": 5}, # This node will extract keywords
                "ui_position": {"x": 300, "y": 50}
            },
            {
                "id": "error_handler_dyn",
                "type": "simple_modifier", # Assuming this exists in NODE_IMPLEMENTATIONS
                "config": {"message_prefix": "Error handled: "},
                "ui_position": {"x": 300, "y": 150}
            }
        ],
        "edges": [
            # No standard edges in this particular example, all conditional from doc_processor_dyn
        ],
        "conditional_edges": [
            {
                "source_node_id": "doc_processor_dyn",
                # router_function_name for this source is taken from doc_processor_dyn's config
                "mappings": [
                    {"condition_name": "high_confidence_path", "target_node_id": "final_summary_node_dyn"},
                    {"condition_name": "low_confidence_path", "target_node_id": "error_handler_dyn"},
                    {"condition_name": "error_handler_path", "target_node_id": "error_handler_dyn"}
                ]
            }
        ],
        "entry_point_node_id": "doc_processor_dyn",
        "terminal_node_ids": ["final_summary_node_dyn", "error_handler_dyn"], # Explicitly define terminal nodes
        "version": 1
    }

    logger.basicConfig(level=logging.DEBUG) # Enable debug logging for builder output

    try:
        builder = DynamicGraphBuilder(example_graph_def_data)
        compiled_graph = builder.build()
        print(f"\nSuccessfully built and compiled graph: {compiled_graph.get_graph().nodes}")

        # To run it (example):
        # import asyncio
        # from .definitions import DocumentProcessingState # Adjust import if needed
        #
        # async def main():
        #     initial_input = DocumentProcessingState(original_document="This is a new test document for dynamic graph.")
        #     async for event in compiled_graph.astream(initial_input, {"recursion_limit": 5}):
        #         print(event)
        #
        # asyncio.run(main())

    except DynamicGraphBuilderError as e:
        print(f"Error building graph: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")