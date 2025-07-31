# 软件自动化补丁回溯工具使用说明

本文档将指导您如何配置和使用软件自动化补丁回溯工具。

## 1. 环境配置与初始化

### 系统环境与依赖

* **系统环境**：推荐使用 Linux 系统，如 Ubuntu 20.04.6 LTS 或 Openeuler 22.03 LTS 等。 
* **环境依赖**：建议在 Conda 环境中运行本工具。  所需的 Python 包已在 `environment.yaml` 文件中列出： 
    ```yaml
    name: sow
    channels:
      - defaults
    dependencies:
      - bs4
      - loguru
      - requests
      - lxml
      - chardet
      - openpyxl
      - pandas
      - tabulate
      - yaml
      - regex
      - ruamel.yaml
      - openai
      - python-dotenv
      - gitpython
      - dashscope
      - tiktoken
      - pyyaml
      - pydantic
      - unidiff
    ```

### 初始化步骤

以 Conda 环境为例，执行以下命令进行环境初始化： 

```bash
# 1. 根据 environment.yaml 文件创建 Conda 环境
conda env create -f environment.yaml

# 2. 激活新创建的环境 (环境名为 environment.yaml 中指定的 'sow')
conda activate sow

# 3. 载入API等环境变量 (需要在项目根目录下有名为 .env 的文件)
source .env
```

## 2. 使用方式与输入

在运行工具前，需要完成以下配置。

### 环境变量配置 (`.env` 文件)

在项目的根目录下创建一个名为 `.env` 的文件。  该文件用于存放与外部服务交互所需的 API 密钥和访问令牌。 

**.env 文件配置示例：** 

```bash
# 用于访问大语言模型服务的API密钥
export OPENAI_API_KEY='sk-...'

# 大语言模型服务的兼容API端点URL
# 如果不了解具体填写规则，可以省略该行，工具会根据配置中的模型名称自动指定
export OPENAI_BASE_URL='[https://dashscope.aliyuncs.com/compatible-mode/v1](https://dashscope.aliyuncs.com/compatible-mode/v1)'

# 用于访问GitHub API和Gitee的个人访问令牌
export GITHUB_TOKEN='ghp_...'
export GITEE_TOKEN='...'
```

### 核心配置文件 (`inputs.yaml`)

本工具的主要行为由一个 YAML 配置文件驱动。  程序默认会加载位于 `~/.config/port-patch/inputs.yaml` 的配置文件。  您可以根据需求修改此文件，或通过命令行的 `--config` 参数指定一个自定义路径。 

**`inputs.yaml` 配置文件示例：** 

```yaml
# 各个模块的专属配置
module_configs:
  compiler:
    extra_flags: -j4
  kernel_compiler:
    ccache_dir: ~/.ccache
    docker_image: kernel-compiler:latest
    enabled: true
    use_docker: true
  llm_adapter:
    temperature: 0.7
    use_enhanced_prompt: true
    
# 项目与执行的基本参数，一般无需更改
config_params:
  build_command: make
  mode: 1
  repo_base_path: ~/.cache/port-patch
  repo_name: jq
  repo_owner: jqlang
  repo_path: /home/elpsy/.cache/port-patch/jq
  response_file: response.txt
  stop_on_failure: false
  use_cached_llm_output: true
  use_cached_patches: false
  
# 流程与模型的优化参数
optimization_params:
  enabled_modules:
  - direct_apply
  - chunk_analyzer
  - llm_adapter
  - patch_adapter
  model: qwen-plus
  prompt_id: backport_file_context_direct_edit
  prompt_template_file: configs/test_prompts.json
  retry_with_feedback: false

# 必需配置（可通过命令行指定）
required:
  branch: 4.0.14
  repo_path: [https://github.com/jqlang/jq/](https://github.com/jqlang/jq/)
  target_version: jq-1.6
  to_commit_list:
  - ad866a1ca3e7d60da888d25d27e46a8adb2ed36e
  - e88f7376fe68dbf4ebaf11fad1513ce700b45860
```

**配置文件参数说明：** 

* **`module_configs`**: 用于对流水线中的各个模块进行精细化配置。 
    * `compiler`: 编译模块的配置，`extra_flags`用于指定额外的编译标志（如`-j4`代表使用4个核心并行编译）。 
    * `kernel_compiler`: 内核编译模块的专属配置，`ccache_dir`指定ccache缓存目录以加速编译，`docker_image`指定用于编译的容器镜像，`use_docker`决定是否在Docker容器中进行编译。 
    * `llm_adapter`: LLM适配模块的配置，`temperature`控制LLM生成内容的多样性，`use_enhanced_prompt`决定是否启用函数级上下文的增强模式以获取更精确的适配结果。 
* **`config_params`**: 定义了项目的基本参数。 
    * `build_command`: 指定执行编译验证时所使用的基础命令，例如`make`。 
    * `mode`: 调试参数，固定为1，代表针对单个（或多个）补丁进行适配。 
    * `repo_base_path`: 用于存放所有本地Git仓库克隆的根目录。 
    * `repo_name`: 当前正在处理的仓库的名称。 
    * `repo_owner`: 当前正在处理的仓库的所有者或组织名。 
    * `repo_path`: 当前正在处理的Git仓库在本地的完整路径。 
    * `response_file`: 指定一个文件名，用于保存LLM返回的原始、未经处理的响应内容。 
    * `stop_on_failure`: 布尔值，若设置为`true`，则流水线中任何一个模块执行失败都会导致整个流程立即中止。 
    * `use_cached_llm_output`: 是否直接使用上一次LLM生成的缓存响应，以节约时间和成本。 
    * `use_cached_patches`: 是否使用已缓存的、之前成功下载或生成的补丁文件，避免重复获取。 
* **`optimization_params`**: 用于控制和优化执行流程。 
    * `enabled_modules`: 一个列表，定义了本次运行将激活哪些处理模块及其执行顺序。 
    * `model`: 指定调用的云端大语言模型名称。 
    * `prompt_id`: 指定在`prompt_template_file`中使用的提示词模板ID。 
    * `prompt_template_file`: 指向一个JSON文件，该文件定义了所有可用的LLM提示词模板。 
    * `retry_with_feedback`: 是否在编译验证失败后，将错误信息反馈给LLM进行迭代式修复。 
* **`required`**: 定义了单次运行必须提供的核心信息（这些参数通常通过命令行动态指定，此处可作为默认值）。 
    * `branch`: 指定操作所基于的分支，在不同场景下可能指代源分支或目标分支。 
    * `repo_path`: 在此处特指待处理补丁所属的远程仓库URL。 
    * `target_version`: 补丁要移植到的目标版本，可以是分支名、标签名或commit SHA。 
    * `to_commit_list`: 一个列表，包含一个或多个需要进行回溯的补丁的commit SHA哈希值或完整URL。 

## 3. 启动方式

本工具通过主脚本 `main.py` 启动，采用命令行参数和配置文件相结合的方式进行控制，其中命令行参数的优先级高于配置文件中的同名参数。 

### 主要命令行参数说明

* `commit_pos` (位置参数): 指定一个或多个需要进行回溯的补丁。  可以是完整的 commit URL，也可以是 commit SHA 哈希值。  若提供多个，请用英文逗号（,）分隔。 
* `--commit_file, -f`: 指定一个文件，其中包含需要回溯的commit URL或hash，每行一个。  当需要处理大量补丁时，推荐使用此方式。 
* `--repo-url, -r` (必填): 指定包含该补丁的远程Git仓库URL。  程序会基于此URL在`repo_base_path`下查找或克隆仓库。 
* `--target, -t` (必填): 指定补丁要移植到的目标版本，可以是分支名、标签名或commit SHA。 
* `--config, -c`: 指定配置文件的路径。  若不提供，则使用默认路径`~/.config/port-patch/inputs.yaml`。 

### 具体指令如下

* **适配单个补丁到指定版本：** 
    ```bash
    python3 main.py <commit_url_or_hash> --repo-url <git_repo_url> --target <target_version>
    ```
    例如： 
    ```bash
    python3 main.py ad866a1ca3 --repo-url [https://github.com/jqlang/jq](https://github.com/jqlang/jq) --target jq-1.6
    ```

* **适配多个补丁到指定版本（使用逗号分隔）：** 
    ```bash
    python3 main.py <commit1>,<commit2> --repo-url <git_repo_url> --target <target_version>
    ```
    例如： 
    ```bash
    python3 main.py ad866a1,e88f737 --repo-url [https://github.com/jqlang/jq](https://github.com/jqlang/jq) --target jq-1.6
    ```

* **通过文件批量适配多个补丁：** 
    ```bash
    python3 main.py --commit-file <path_to_file> --repo-url <git_repo_url> --target <target_version>
    ```
    例如，假设 `my_commits.txt` 文件内容为: 
    ```
    ad866a1ca3e7d60da888d25d27e46a8adb2ed36e
    e88f7376fe68dbf4ebaf11fad1513ce700b45860
    ```
    则指令为： 
    ```bash
    python3 main.py --commit-file my_commits.txt --repo-url [https://github.com/jqlang/jq](https://github.com/jqlang/jq) --target jq-1.6
    ```

## 4. 输出结果

工具执行完成后，会生成一系列结构化的输出文件，用于记录处理结果、提供最终产物以及便于调试分析。 

### 中间过程工作区 (`workspace`)

所有中间产物和详细日志都保存在项目根目录下的 `workspace/` 中，其结构如下： 
```
workspace/<repo_owner>/<repo_name>/<commit_short_sha>/
```
该目录下包含： 

* `patches/`：存放原始下载的补丁和各阶段生成的补丁文件。 
* `chunk_patches/`：存放由补丁分块分析模块生成的各个独立的补丁块文件，以及未应用成功的“剩余补丁”。 
* `llm_output/`：存放LLM适配模块的输出，包括LLM返回的原始响应和解析后的补丁文件。 
* `evaluations/`：存放每个模块的评估信息，通常包含输入、输出和执行指标的详细记录，便于对特定模块的性能进行分析。 

### 最终结果目录 (`results`)

每次运行的最终结果都保存在一个以任务信息和时间戳命名的独立目录中，其结构如下： 
```
results/<repo_name>_<target_version>_<commit_short_sha>_<timestamp>/
```
该目录下包含核心产出物： 

* `result.json`：本次任务最全面的JSON格式报告。  它详细记录了输入的配置、各模块的执行结果、错误信息、执行耗时、最终的适配状态摘要等。 
* `merged_{target_version}.patch`：若补丁适配成功，会生成此文件。  这是由补丁重构引擎将所有成功应用的修改片段合并后生成的最终补丁，可直接应用于目标版本。 
