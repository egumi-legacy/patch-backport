from pathlib import Path
from ruamel.yaml import YAML
import pprint
from llm_assistant import LLMAssistant
from patch_processor import PatchProcessor

_DEFAULT_INPUT_FILE = Path(__file__).parent / "inputs.yaml"

class Main:
    def __init__(self):
        with open(_DEFAULT_INPUT_FILE, "r") as file:
            inputs = YAML().load(file)

        pprint.pprint(inputs)
        self.inputs = inputs
        

    def run(self):
        # self.inputs["prompt_values"] = ['hello', 'world']
        # llm_output = LLMAssistant(self.inputs).run()
        
        # for response in llm_output["openai_responses"]:
        #     print(f"response: {response}")

        patch_processor = PatchProcessor(self.inputs)
        patch_processor.run()

if __name__ == "__main__":
    main = Main()
    main.run()