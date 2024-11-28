from __future__ import annotations

from patchwork.step import Step, StepStatus
from patchwork.steps import ModifyCode
from patchwork.steps.ModifyCodePB.typed import ModifyCodePBInputs, ModifyCodePBOutputs


class ModifyCodePB(Step, input_class=ModifyCodePBInputs, output_class=ModifyCodePBOutputs):
    def __init__(self, inputs: dict):
        super().__init__(inputs)
        self.file_path = inputs["file_path"]
        self.start_line = inputs.get("start_line")
        self.end_line = inputs.get("end_line")
        self.patch = inputs.get("new_code")

    def run(self) -> dict:
        if self.patch is None:
            self.set_status(StepStatus.SKIPPED, "No patch provided")
            return {}

        modify_code = ModifyCode(
            {
                "files_to_patch": [
                    dict(
                        uri=self.file_path,
                        startLine=self.start_line,
                        endLine=self.end_line,
                    )
                ],
                "extracted_responses": [
                    dict(
                        patch=self.patch,
                    )
                ],
            }
        )
        modified_code_files = modify_code.run()
        return modified_code_files.get("modified_code_files", [{}])[0]

class ModifyCode(Step):
    UPDATED_SNIPPETS_KEY = "extracted_responses"
    FILES_TO_PATCH = "files_to_patch"
    required_keys = {FILES_TO_PATCH, UPDATED_SNIPPETS_KEY}

    def __init__(self, inputs: dict):
        super().__init__(inputs)
        if not all(key in inputs.keys() for key in self.required_keys):
            raise ValueError(f'Missing required data: "{self.required_keys}"')

        self.files_to_patch = inputs[self.FILES_TO_PATCH]
        self.extracted_responses = inputs[self.UPDATED_SNIPPETS_KEY]

    def run(self) -> dict:
        modified_code_files = []
        sorted_list = sorted(
            zip(self.files_to_patch, self.extracted_responses), key=lambda x: x[0]["startLine"], reverse=True
        )
        if len(sorted_list) == 0:
            # self.extracted_responses
            self.set_status(StepStatus.SKIPPED, "No code snippets to modify.")
            return dict(modified_code_files=[])

        for code_snippet, extracted_response in sorted_list:
            uri = code_snippet.get("uri")
            start_line = code_snippet.get("startLine")
            end_line = code_snippet.get("endLine")
            new_code = extracted_response.get("patch")
            if new_code is None:
                continue

            replace_code_in_file(uri, start_line, end_line, new_code)
            modified_code_file = dict(path=uri, start_line=start_line, end_line=end_line, **extracted_response)
            modified_code_files.append(modified_code_file)

        return dict(modified_code_files=modified_code_files)