from pathlib import Path
from ruamel.yaml import YAML
import pprint


_DEFAULT_INPUT_FILE = Path(__file__).parent / "inputs.yaml"

class Main:
    def __init__(self):
        with open(_DEFAULT_INPUT_FILE, "r") as file:
            inputs = YAML().load(file)

        pprint.pprint(inputs)

        self.inputs = inputs

        self.llm_assistant = LLMAssistant(self.inputs)

    def run(self):
        llm_output = self.llm_assistant.run()
        self.llm_assistant.run()

if __name__ == "__main__":
    main = Main()
    # main.run()