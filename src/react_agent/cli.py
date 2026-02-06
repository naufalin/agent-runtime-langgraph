import argparse

from langchain_core.messages import HumanMessage

from .graph import graph
from .observability import get_callbacks, session_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ReAct agent.")
    parser.add_argument("prompt", nargs="*", help="Prompt text")
    parser.add_argument(
        "--thread",
        default="default",
        help="Thread id for persistence/checkpointing",
    )
    args = parser.parse_args()

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        prompt = input("User: ").strip()
    inputs = {"messages": [HumanMessage(content=prompt)]}
    config = {"configurable": {"thread_id": args.thread}}
    callbacks = get_callbacks()
    if callbacks:
        config["callbacks"] = callbacks
        metadata = session_metadata(args.thread)
        if metadata:
            config["metadata"] = metadata

    final_message = None
    for event in graph.stream(inputs, stream_mode="values", config=config):
        final_message = event["messages"][-1]

    if final_message is not None:
        print(final_message.content)


if __name__ == "__main__":
    main()
