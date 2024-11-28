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
        patch_processor = PatchProcessor(self.inputs)
        patch_processor_outputs = patch_processor.run()
        self.inputs.update(patch_processor_outputs)

        use_cache = self.inputs.get("use_cache", False)
        if use_cache:
            self.inputs["cache_path"] = self.patch_processor.get_response_path()
        
        
        # self.inputs["prompt_values"] = ['hello', 'world']
        llm_output = LLMAssistant(self.inputs).run()
        self.inputs.update(llm_output)
        

        
        # output_file_name = f"output_{self.inputs['target_version']}_{self.inputs['model']}"
        # output_path = self.inputs['basedir'] / output_file_name
        for response in llm_output["openai_responses"]:
            # if not output_path.exists():
            if not use_cache:
                output_path = patch_processor.save_response_to_project(response)
            else:
                output_path = self.inputs["cache_path"]

            patch_processor.apply_llm_patch(output_path)
            patch_processor.generate_folder_diff(
                self.inputs['basedir'] / self.inputs['target_version'], 
                self.inputs['basedir'] / f'adapted_{self.inputs["target_version"]}', 
                self.inputs['basedir'] / f'adapted_diff_{self.inputs["target_version"]}'
            )
            
                
            
        #     print(f"response: {response}")
        # if output_path is not None:
        #         patch_processor.apply_llm_patch(output_path)


        # output_path = Path('patchfile/redis_redis_c8649f/output_4.0.11_qwen-plus')
        # patch_processor.apply_llm_patch(output_path)

        
        

        

if __name__ == "__main__":
    main = Main()
    main.run()