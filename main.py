from core.agent import Agent
from core.memory import init_db

init_db()
agent = Agent(user_id="cli_user")
print("Agent ready! Type 'quit' to exit, 'clear' to reset history.\n")

while True:
    user_input = input("You: ").strip()
    if not user_input:
        continue
    if user_input.lower() == "quit":
        print("Bye!")
        break
    if user_input.lower() == "clear":
        from core.memory import clear_history
        clear_history("cli_user")
        print("历史已清空\n")
        continue
    response = agent.run(user_input)
    print(f"Agent: {response}\n")
