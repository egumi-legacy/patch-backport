class PatchAdapter:
    def __init__(self, input):
        self.file_path = input

    def apply_llm_patch(self, llm_response_path):
        """
        将 LLM 生成的 patch 应用到旧版本的源文件
        
        :param llm_response_path: LLM 生成的响应内容路径
        """
        llm_response = llm_response_path.read_text()
        logger.info("test--------------")
        
        base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"
        target_dir = base_dir / self.target_version
        output_dir = base_dir / f"adapted_{self.target_version}"
        
        # 解析 LLM 响应，提取每个文件的 diff
        current_file = None
        current_diff = []
        files_to_patch = {}
        
        for line in llm_response.splitlines():
            if line.startswith('diff --git'):
                if current_file and current_diff:
                    files_to_patch[current_file] = '\n'.join(current_diff)
                # 从 diff --git a/path/to/file b/path/to/file 提取文件路径
                current_file = line.split(' ')[-1][2:] # 取 b/path/to/file 并去掉 b/
                current_diff = []
                continue
            if line.startswith('index '):
                continue
            if current_file:
                current_diff.append(line)
        
        # 添加最后一个文件的 diff
        if current_file and current_diff:
            files_to_patch[current_file] = '\n'.join(current_diff)
        
        # 创建输出目录
        if not output_dir.exists():
            output_dir.mkdir(parents=True)
        
        # 应用修改到每个文件
        for file_path, diff_content in files_to_patch.items():
            source_file = target_dir / file_path
            target_file = output_dir / file_path
            
            if not source_file.exists():
                logger.error(f"源文件不存在: {source_file}")
                continue
                
            # 确保目标目录存在
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 应用 diff
            try:
                self._apply_patch_to_file(diff_content, source_file, target_file)
                logger.info(f"成功应用修改到文件: {file_path}")
            except Exception as e:
                logger.error(f"应用修改到文件 {file_path} 时出错: {str(e)}")

    def _apply_patch_to_file(self, diff_content, source_file, target_file):
        """Enhanced patch application with structural validation"""
        def find_function_definition(lines, func_name):
            """Find the exact function definition with more flexible matching"""
            # 更灵活的函数定义模式，允许多行定义
            pattern = re.compile(rf'^(?:static\s+)?(?:int|void|char\s*\*)\s+{re.escape(func_name)}\s*\(.*?(?:\)|\n)')
            
            for i, line in enumerate(lines):
                if pattern.match(line.strip()):
                    # 如果函数定义跨多行，找到完整定义
                    if not line.strip().endswith(')'):
                        bracket_count = line.count('(') - line.count(')')
                        j = i + 1
                        while j < len(lines) and bracket_count > 0:
                            bracket_count += lines[j].count('(') - lines[j].count(')')
                            j += 1
                        if bracket_count == 0:
                            return i
                    else:
                        return i
            return None

        def find_function_bounds(lines, start_line):
            """Find function bounds with improved bracket matching"""
            if start_line is None:
                return None, None
            
            # 从函数定义开始查找开括号
            bracket_count = 0
            found_opening = False
            current_line = start_line
            
            # 首先找到函数定义结束和开括号
            while current_line < len(lines):
                line = lines[current_line]
                # 计算当前行的括号
                bracket_count += line.count('{') - line.count('}')
                
                if '{' in line:
                    found_opening = True
                    break
                    
                current_line += 1
                
                # 如果搜索太远还没找到开括号，可能是出错了
                if current_line - start_line > 10:  # 设置合理的搜索范围
                    return None, None
            
            if not found_opening:
                return None, None
            
            # 继续查找直到找到匹配的闭括号
            for i in range(current_line + 1, len(lines)):
                bracket_count += lines[i].count('{') - lines[i].count('}')
                if bracket_count == 0:
                    return start_line, i
            
            return None, None

        def validate_structure(lines):
            """Validate basic code structure"""
            bracket_count = 0
            for line in lines:
                bracket_count += line.count('{') - line.count('}')
            return bracket_count == 0

        with open(source_file, 'r', encoding='utf-8') as f:
            original_lines = f.readlines()

        # Parse hunks and group by function
        function_changes = {}
        for hunk in self._parse_hunks(diff_content):
            if hunk['function']:
                # 提取函数名，处理可能的函数签名变化
                func_match = re.search(r'\b(\w+)\s*\(', hunk['function'])
                if func_match:
                    func_name = func_match.group(1)
                    if func_name not in function_changes:
                        function_changes[func_name] = []
                    function_changes[func_name].append(hunk)
                    logger.debug(f"Found changes for function: {func_name}")

        # Apply changes function by function
        new_lines = original_lines[:]
        modified = False
        
        for func_name, hunks in function_changes.items():
            logger.debug(f"Processing function: {func_name}")
            
            # Find function definition
            func_start = find_function_definition(new_lines, func_name)
            if func_start is None:
                logger.error(f"Could not find function definition: {func_name}")
                continue
            
            # Find function bounds
            start, end = find_function_bounds(new_lines, func_start)
            if start is None:
                logger.error(f"Could not find function bounds: {func_name}")
                continue

            logger.debug(f"Found function {func_name} from line {start} to {end}")

            # Apply changes within function bounds
            function_lines = new_lines[start:end + 1]
            modified_lines = self._apply_changes_to_function(
                function_lines,
                hunks,
                func_name
            )

            # Validate and replace
            if validate_structure(modified_lines):
                if modified_lines != function_lines:  # 只有在实际有修改时才替换
                    new_lines[start:end + 1] = modified_lines
                    modified = True
                    logger.info(f"Successfully modified function: {func_name}")
            else:
                logger.error(f"Invalid structure after modifying {func_name}")

        # Only write if there were actual modifications
        if modified:
            with open(target_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            logger.info(f"Successfully wrote changes to {target_file}")
        else:
            logger.warning("No modifications were made to the file")

    def _apply_changes_to_function(self, function_lines, hunks, func_name):
        """Apply changes to a single function with enhanced content matching"""
        modified_lines = function_lines[:]
        
        for hunk in hunks:
            # 使用更灵活的内容匹配
            position = self._find_best_match_position(
                modified_lines,
                hunk['context_before'],
                hunk['context_after'],
                threshold=0.7  # 降低阈值以允许更多的近似匹配
            )
            
            if position is not None:
                # Create backup
                backup_lines = modified_lines[:]
                
                try:
                    self._apply_hunk_changes(
                        modified_lines,
                        position,
                        hunk['removed_lines'],
                        hunk['added_lines'],
                        similarity_threshold=0.7  # 降低相似度要求
                    )
                    
                    # 验证修改后的代码结构
                    if not self._validate_function_structure(modified_lines):
                        logger.warning(f"Invalid structure after changes in {func_name}, rolling back")
                        modified_lines = backup_lines
                except Exception as e:
                    logger.error(f"Error applying changes to {func_name}: {str(e)}")
                    modified_lines = backup_lines
        
        return modified_lines

    def _parse_hunks(self, diff_content):
        """解析 diff 内容，提取每个 hunk 的上下文和修改内容"""
        hunks = []
        current_hunk = None
        
        # 用于跟踪当前正在处理的函数
        current_function = None
        
        for line in diff_content.splitlines():
            # 检测函数定义
            if re.match(r'^[+-]?\s*(?:static\s+)?(?:int|void|char\s*\*)\s+\w+\s*\(', line):
                current_function = line.strip()
                if current_function.startswith(('+', '-')):
                    current_function = current_function[1:]
            
            # 跳过文件头
            if line.startswith(('---', '+++', 'index', 'diff --git')):
                continue
            
            # 新的 hunk 开始
            if line.startswith('@@'):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {
                    'function': current_function,
                    'content': line + '\n',
                    'context_before': [],
                    'context_after': [],
                    'removed_lines': [],
                    'added_lines': [],
                    'in_change': False
                }
                continue
            
            if not current_hunk:
                continue
            
            current_hunk['content'] += line + '\n'
            
            if line.startswith(' '):
                if current_hunk['in_change']:
                    current_hunk['context_after'].append(line[1:])
                else:
                    current_hunk['context_before'].append(line[1:])
            elif line.startswith('-'):
                current_hunk['in_change'] = True
                current_hunk['removed_lines'].append(line[1:])
            elif line.startswith('+'):
                current_hunk['in_change'] = True
                current_hunk['added_lines'].append(line[1:])
        
        if current_hunk:
            hunks.append(current_hunk)
        
        return hunks

    def _find_best_match_position(self, context_before, context_after, file_lines, 
                                context_size=3, threshold=0.8):
        """
        使用上下文匹配找到最佳修改位置
        
        :param context_before: 修改前的上下文行
        :param context_after: 修改后的上下文行
        :param file_lines: 文件的所有行
        :param context_size: 匹配的上下文大小
        :param threshold: 匹配度阈值
        :return: 最佳匹配位置，如果没有找到好的匹配则返回 None
        """
        if not context_before and not context_after:
            return None
            
        best_match_score = 0
        best_position = None
        
        # 构建上下文匹配字符串
        context_str = ''.join(context_before + context_after)
        
        # 在文件中滑动窗口寻找最佳匹配
        for i in range(len(file_lines) - len(context_before + context_after) + 1):
            window = file_lines[i:i + len(context_before + context_after)]
            window_str = ''.join(window)
            
            # 计算匹配度
            matcher = SequenceMatcher(None, context_str, window_str)
            score = matcher.ratio()
            
            if score > best_match_score:
                best_match_score = score
                best_position = i + len(context_before)
        
        # 如果最佳匹配超过阈值，返回位置
        if best_match_score >= threshold:
            return best_position
        
        # 如果没有找到好的匹配，尝试只匹配前后文的一部分
        if len(context_before) > context_size:
            context_before = context_before[-context_size:]
        if len(context_after) > context_size:
            context_after = context_after[:context_size]
            
        return self._find_best_match_position(context_before, context_after, 
                                            file_lines, context_size, threshold - 0.1)

    def _apply_hunk_changes(self, lines, position, removed_lines, added_lines, similarity_threshold=0.7):
        """Apply changes with more flexible matching"""
        # 获取实际要修改的行
        actual_lines = lines[position:position + len(removed_lines)]
        
        # 使用更灵活的内容匹配
        if self._lines_match(actual_lines, removed_lines, threshold=similarity_threshold):
            # 删除旧行
            del lines[position:position + len(removed_lines)]
            # 插入新行
            for i, line in enumerate(added_lines):
                if not line.endswith('\n'):
                    line += '\n'
                lines.insert(position + i, line)
        else:
            logger.warning(f"Content mismatch. Expected:\n{''.join(removed_lines)}\nActual:\n{''.join(actual_lines)}")
            # 强制应用修改，但保留日志
            del lines[position:position + len(removed_lines)]
            for i, line in enumerate(added_lines):
                if not line.endswith('\n'):
                    line += '\n'
                lines.insert(position + i, line)

    def _lines_match(self, lines1, lines2, threshold=0.8):
        """
        检查两组行是否匹配
        
        :param lines1: 第一组行
        :param lines2: 第二组行
        :param threshold: 匹配度阈值
        :return: 是否匹配
        """
        if not lines1 or not lines2:
            return False
            
        text1 = ''.join(lines1)
        text2 = ''.join(lines2)
        
        matcher = SequenceMatcher(None, text1, text2)
        return matcher.ratio() >= threshold

    def _find_anchor_points(self, context_lines):
        """
        在上下文中找到可以作为锚点的唯一可识别点
        返回一个 (pattern, type) 元组列表
        """
        anchors = []
        
        for line in context_lines:
            # 查找函数调用
            if re.search(r'\w+\([^)]*\)', line):
                func_call = re.search(r'(\w+\([^)]*\))', line).group(1)
                anchors.append((func_call, 'function_call'))
            
            # 查找控制结构
            elif any(keyword in line for keyword in ['if', 'for', 'while', 'switch', 'return']):
                control = line.strip()
                anchors.append((control, 'control_structure'))
            
            # 查找变量声明
            elif re.search(r'^\s*\w+\s+\w+\s*[=;]', line):
                declaration = line.strip()
                anchors.append((declaration, 'declaration'))
        
        return anchors

    def _find_position_with_anchors(self, lines, context_before, context_after, anchors):
        """
        使用锚点和上下文找到最佳修改位置
        """
        best_position = None
        best_score = 0
        
        # 如果有锚点，首先尝试使用锚点定位
        for anchor, anchor_type in anchors:
            for i, line in enumerate(lines):
                if anchor in line:
                    # 验证周围上下文
                    context_score = self._verify_surrounding_context(
                        lines, i, context_before, context_after
                    )
                    if context_score > best_score:
                        best_score = context_score
                        best_position = i
        
        # 如果没有找到好的锚点匹配，回退到普通上下文匹配
        if best_score < 0.8:
            best_position = self._find_best_match_position(
                context_before, context_after, lines
            )
        
        return best_position

    def _verify_surrounding_context(self, lines, position, context_before, context_after, 
                                  context_size=3):
        """
        验证给定位置周围的上下文匹配程度
        返回0-1之间的匹配分数
        """
        start = max(0, position - len(context_before))
        end = min(len(lines), position + len(context_after))
        
        # 获取实际上下文
        actual_context = lines[start:end]
        expected_context = context_before + context_after
        
        # 使用序列匹配计算相似度
        matcher = SequenceMatcher(None, 
                                ''.join(actual_context), 
                                ''.join(expected_context))
        return matcher.ratio()

    def _validate_function_structure(self, lines):
        """
        验证函数结构的完整性
        检查括号匹配、基本语法等
        """
        # 检查括号平衡
        bracket_count = 0
        for line in lines:
            bracket_count += line.count('{') - line.count('}')
            # 括号数不能小于0
            if bracket_count < 0:
                return False
        
        # 最终括号应该平衡
        if bracket_count != 0:
            return False
        
        # 检查基本语法结构
        for line in lines:
            # 检查未闭合的字符串
            if line.count('"') % 2 != 0:
                return False
            
            # 检查分号结尾（忽略预处理指令、花括号行等）
            stripped = line.strip()
            if (stripped and 
                not stripped.startswith('#') and 
                not stripped.endswith('{') and 
                not stripped.endswith('}') and 
                not stripped.endswith(';')):
                return False
        
        return True