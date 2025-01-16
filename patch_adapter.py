import requests
import re
import dotenv
import pprint
import os
import subprocess
import base64
from pathlib import Path
from llm_assistant import LLMAssistant
from loguru import logger
import difflib
from difflib import SequenceMatcher
from typing import List
import html

class PatchAdapter:
    def __init__(self, similarity_threshold=0.7):
        self.similarity_threshold = similarity_threshold
        # self.base_dir = input["basedir"]


    def parse_hunk(self, hunk_text):
        # """解析patch中的一个hunk"""
        # # 解析hunk头
        # lines = hunk_text.split('\n')
        # header_match = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)', lines[0])
        # if not header_match:
        #     raise ValueError("Invalid hunk header")
        
        # # 跟踪连续的修改块
        # changes = []  # 存储所有修改块
        # current_change = {
        #     'context_before': [],
        #     'context_after': [],
        #     'removed_lines': [],
        #     'added_lines': []
        # }
        
        # lines = lines[1:]  # 跳过header行
        # i = 0
        # while i < len(lines):
        #     line = lines[i]
        #     if not line:
        #         i += 1
        #         continue
                
        #     # 处理修改行
        #     if line.startswith('-') or line.startswith('+'):
        #         # 收集前置上下文（向前看最多3行）
        #         if not current_change['removed_lines'] and not current_change['added_lines']:
        #             start = max(0, i - 3)
        #             current_change['context_before'] = [l[1:] for l in lines[start:i] if l.startswith(' ')]
                
        #         # 收集修改行
        #         if line.startswith('-'):
        #             current_change['removed_lines'].append(line[1:])
        #         else:
        #             current_change['added_lines'].append(line[1:])
                    
        #         # 查看后面的行，收集后置上下文
        #         next_change_pos = i + 1
        #         while (next_change_pos < len(lines) and 
        #             (not lines[next_change_pos] or lines[next_change_pos].startswith(' '))):
        #             if lines[next_change_pos] and lines[next_change_pos].startswith(' '):
        #                 current_change['context_after'].append(lines[next_change_pos][1:])
        #             next_change_pos += 1
                
        #         # 如果遇到下一个修改块，保存当前块并开始新的块
        #         if (next_change_pos < len(lines) and 
        #             (lines[next_change_pos].startswith('-') or lines[next_change_pos].startswith('+'))):
        #             if current_change['removed_lines'] or current_change['added_lines']:
        #                 changes.append(current_change)
        #                 current_change = {
        #                     'context_before': [],
        #                     'context_after': [],
        #                     'removed_lines': [],
        #                     'added_lines': []
        #                 }
                
        #         i = next_change_pos - 1  # 减1是因为循环末尾会加1
                
        #     i += 1
        
        # # 添加最后一个修改块
        # if current_change['removed_lines'] or current_change['added_lines']:
        #     changes.append(current_change)
        
        # return changes

        
        # """解析patch中的一个hunk"""
        # lines = hunk_text.split('\n')
        # header_match = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)', lines[0])
        # if not header_match:
        #     raise ValueError("Invalid hunk header")
        
        # hunks = []
        # current_hunk = {
        #     'context_before': [],
        #     'context_after': [],
        #     'removed_lines': [],
        #     'added_lines': []
        # }
        
        # context_lines = []
        # in_modification = False
        
        # for line in lines[1:]:
        #     # 跳过空行
        #     if not line:
        #         continue
                
        #     # 清理行中可能的特殊字符
        #     line = line.replace('``', '').rstrip()
            
        #     if line.startswith(' '):
        #         content = line[1:]
        #         if in_modification:
        #             if len(context_lines) >= 3:
        #                 current_hunk['context_after'] = context_lines[:3]
        #                 if current_hunk['removed_lines'] or current_hunk['added_lines']:
        #                     hunks.append(current_hunk)
        #                     current_hunk = {
        #                         'context_before': context_lines[-3:],
        #                         'context_after': [],
        #                         'removed_lines': [],
        #                         'added_lines': []
        #                     }
        #                 context_lines = []
        #                 in_modification = False
        #             else:
        #                 context_lines.append(content)
        #         else:
        #             context_lines.append(content)
        #     else:
        #         if not in_modification:
        #             current_hunk['context_before'] = context_lines[-3:] if context_lines else []
        #             context_lines = []
        #             in_modification = True
                
        #         if line.startswith('-'):
        #             current_hunk['removed_lines'].append(line[1:])
        #         elif line.startswith('+'):
        #             # 只有当内容不为空时才添加
        #             content = line[1:]
        #             if content and content != '``':
        #                 current_hunk['added_lines'].append(content)
        
        # # 处理最后的上下文和修改块
        # if context_lines:
        #     current_hunk['context_after'] = context_lines[:3]
        # if current_hunk['removed_lines'] or current_hunk['added_lines']:
        #     hunks.append(current_hunk)
        
        # return hunks

        # """解析patch中的一个hunk"""
        # lines = hunk_text.split('\n')
        # header_match = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)', lines[0])
        # if not header_match:
        #     raise ValueError("Invalid hunk header")
        
        # hunks = []
        # current_hunk = {
        #     'context_before': [],
        #     'context_after': [],
        #     'changes': []  # 新的结构，存储修改序列
        # }
        
        # context_lines = []
        # in_modification = False
        
        # for line in lines[1:]:
        #     if not line:
        #         continue
                
        #     line = line.replace('``', '').rstrip()
            
        #     if line.startswith(' '):
        #         content = line[1:]
        #         if in_modification:
        #             # 如果这个未修改的行在修改块中间，将其作为修改序列的一部分
        #             if len(context_lines) < 3 and content not in [c[1] for c in current_hunk['changes']]:
        #                 current_hunk['changes'].append(('keep', content))
        #                 context_lines.append(content)
        #             else:
        #                 # 结束当前修改块
        #                 current_hunk['context_after'] = context_lines[:3]
        #                 if current_hunk['changes']:
        #                     hunks.append(current_hunk)
        #                     current_hunk = {
        #                         'context_before': context_lines[-3:],
        #                         'context_after': [],
        #                         'changes': []
        #                     }
        #                 context_lines = []
        #                 in_modification = False
        #         else:
        #             context_lines.append(content)
        #     else:
        #         if not in_modification:
        #             current_hunk['context_before'] = context_lines[-3:] if context_lines else []
        #             context_lines = []
        #             in_modification = True

        #         # 处理空行
        #         if line == '-' or line == '+':
        #             if line == '+':
        #                 current_hunk['changes'].append(('add', ''))
        #             continue
                
        #         if line.startswith('-'):
        #             current_hunk['changes'].append(('remove', line[1:]))
        #         elif line.startswith('+'):
        #             content = line[1:]
        #             if content and content != '``':
        #                 current_hunk['changes'].append(('add', content))
        
        # if context_lines:
        #     current_hunk['context_after'] = context_lines[:3]
        # if current_hunk['changes']:
        #     hunks.append(current_hunk)
        
        # return hunks

        # """解析patch中的一个hunk"""
        # lines = hunk_text.split('\n')
        # header_match = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)', lines[0])
        # if not header_match:
        #     raise ValueError("Invalid hunk header")
        
        # hunks = []
        # current_hunk = {
        #     'context_before': [],
        #     'context_after': [],
        #     'changes': []
        # }
        
        # context_lines = []
        # in_modification = False
        
        # for line in lines[1:]:
        #     if not line:
        #         continue
                
        #     line = line.replace('``', '').rstrip()
            
        #     if line.startswith(' '):
        #         content = line[1:]
        #         if in_modification:
        #             # 仅在结束修改块时处理上下文
        #             current_hunk['context_after'].append(content)
        #             if len(current_hunk['context_after']) >= 3:
        #                 if current_hunk['changes']:
        #                     hunks.append(current_hunk)
        #                 current_hunk = {
        #                     'context_before': current_hunk['context_after'][-3:],
        #                     'context_after': [],
        #                     'changes': []
        #                 }
        #                 in_modification = False
        #         else:
        #             context_lines.append(content)
        #     else:
        #         if not in_modification:
        #             current_hunk['context_before'] = context_lines[-3:] if context_lines else []
        #             context_lines = []
        #             in_modification = True
        #             current_hunk['context_after'] = []
                
        #         if line == '-':
        #             current_hunk['changes'].append(('remove', ''))
        #         elif line == '+':
        #             current_hunk['changes'].append(('add', ''))
        #         elif line.startswith('-'):
        #             current_hunk['changes'].append(('remove', line[1:]))
        #         elif line.startswith('+'):
        #             content = line[1:]
        #             if content and content != '``':
        #                 current_hunk['changes'].append(('add', content))
        
        # # 处理最后的上下文
        # if context_lines:
        #     current_hunk['context_after'] = context_lines[:3]
        # if current_hunk['changes']:
        #     hunks.append(current_hunk)
        
        # return hunks

        lines = hunk_text.split('\n')
        header_match = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)', lines[0])
        if not header_match:
            raise ValueError("Invalid hunk header")
        
        # 存储解析结果
        parsed_lines = []
        current_block = []
        
        # 解析每一行
        for line in lines[1:]:
            if not line:
                continue
                
            # 根据行首字符确定类型
            if line.startswith('-'):
                parsed_lines.append(('remove', line[1:].rstrip()))
            elif line.startswith('+'):
                parsed_lines.append(('add', line[1:].rstrip()))
            elif line.startswith(' '):
                parsed_lines.append(('context', line[1:].rstrip()))
        
        # 构建hunk结构
        hunk = {
            'line_numbers': {
                'old_start': int(header_match.group(1)),
                'old_count': int(header_match.group(2)),
                'new_start': int(header_match.group(3)),
                'new_count': int(header_match.group(4))
            },
            'lines': parsed_lines
        }
        
        return [hunk]
        

    # def find_best_match_position(self, file_lines, hunk):
    #     """找到hunk最佳匹配位置"""
    #     best_position = -1
    #     best_score = 0
        
    #     # 使用删除行作为主要锚点
    #     anchor_text = '\n'.join(hunk['removed_lines'])
    #     context_before = '\n'.join(hunk['context_before'])
    #     context_after = '\n'.join(hunk['context_after'])
        
    #     # 在文件中滑动窗口寻找最佳匹配
    #     for i in range(len(file_lines)):
    #         # 检查删除行匹配
    #         potential_removed = '\n'.join(file_lines[i:i + len(hunk['removed_lines'])])
    #         removed_similarity = SequenceMatcher(None, anchor_text, potential_removed).ratio()
            
    #         if removed_similarity < self.similarity_threshold:
    #             continue
                
    #         # 检查前后上下文
    #         context_before_text = '\n'.join(file_lines[max(0, i - len(hunk['context_before'])):i])
    #         context_after_text = '\n'.join(file_lines[i + len(hunk['removed_lines']):
    #                                                 i + len(hunk['removed_lines']) + len(hunk['context_after'])])
            
    #         before_similarity = SequenceMatcher(None, context_before, context_before_text).ratio()
    #         after_similarity = SequenceMatcher(None, context_after, context_after_text).ratio()
            
    #         # 计算综合得分
    #         score = (removed_similarity * 0.65 +  # 删除行权重更高
    #                 before_similarity * 0.15 +
    #                 after_similarity * 0.2)
            
    #         if score > 0.5:  # 只打印相对高的分数
    #             logger.debug(f"Position {i} total score: {score}")
    #             logger.debug(f"Before similarity: {before_similarity}")
    #             logger.debug(f"After similarity: {after_similarity}")
                    
    #         if score > best_score:
    #             best_score = score
    #             best_position = i
                
    #     return best_position if best_score >= self.similarity_threshold else -1

    # def find_best_match_position(self, file_lines, hunk):
    #     """找到hunk最佳匹配位置"""
    #     best_position = -1
    #     best_score = 0
        
    #     # 从changes中提取删除的行
    #     removed_lines = [content for change_type, content in hunk['changes'] 
    #                     if change_type == 'remove']
    #     if not removed_lines:
    #         # 如果没有删除的行，尝试使用上下文
    #         return self.find_position_by_context(file_lines, hunk)
        
    #     # 清理行尾的空白字符
    #     file_lines = [line.rstrip() for line in file_lines]
        
    #     # 准备比较文本
    #     anchor_text = '\n'.join(removed_lines)
    #     context_before = '\n'.join(hunk['context_before'])
    #     context_after = '\n'.join(hunk['context_after'])
        
    #     # 在文件中滑动窗口寻找最佳匹配
    #     for i in range(len(file_lines)):
    #         # 检查删除行匹配
    #         potential_removed = '\n'.join(file_lines[i:i + len(removed_lines)])
    #         removed_similarity = SequenceMatcher(None, anchor_text, potential_removed).ratio()
            
    #         if removed_similarity < self.similarity_threshold:
    #             continue
                
    #         # 检查前后上下文
    #         context_before_text = '\n'.join(file_lines[max(0, i - len(hunk['context_before'])):i])
    #         context_after_text = '\n'.join(file_lines[i + len(removed_lines):
    #                                     i + len(removed_lines) + len(hunk['context_after'])])
            
    #         before_similarity = SequenceMatcher(None, context_before, context_before_text).ratio()
    #         after_similarity = SequenceMatcher(None, context_after, context_after_text).ratio()
            
    #         # 计算综合得分
    #         score = (removed_similarity * 0.7 +
    #                 before_similarity * 0.15 +
    #                 after_similarity * 0.15)
            
    #         if score > best_score:
    #             best_score = score
    #             best_position = i
                
    #     return best_position if best_score >= self.similarity_threshold else -1
    def find_best_match_position(self, file_lines, hunk):
        """找到hunk最佳匹配位置"""
        best_position = -1
        best_score = 0
        
        # 获取hunk中的上下文行
        context_lines = []
        for line_type, content in hunk['lines']:
            if line_type in ('context', 'remove'):
                context_lines.append(content)
        
        # 在文件中查找匹配
        for i in range(len(file_lines)):
            score = 0
            matches = 0
            
            # 比较每一行
            for j, context_line in enumerate(context_lines):
                if (i + j < len(file_lines) and 
                    file_lines[i + j].rstrip() == context_line):
                    matches += 1
                    
            if matches > 0:
                score = matches / len(context_lines)
                if score > best_score:
                    best_score = score
                    best_position = i
        
        return best_position if best_score >= self.similarity_threshold else -1

    def find_position_by_context(self, file_lines, hunk):
        """当没有删除行时，通过上下文查找位置"""
        context_before = '\n'.join(hunk['context_before'])
        context_after = '\n'.join(hunk['context_after'])
        
        for i in range(len(file_lines)):
            context_before_text = '\n'.join(file_lines[max(0, i - len(hunk['context_before'])):i])
            context_after_text = '\n'.join(file_lines[i:i + len(hunk['context_after'])])
            
            before_similarity = SequenceMatcher(None, context_before, context_before_text).ratio()
            after_similarity = SequenceMatcher(None, context_after, context_after_text).ratio()
            
            if before_similarity > self.similarity_threshold and after_similarity > self.similarity_threshold:
                return i
                
        return -1

    def apply_hunk(self, file_lines, position, hunk):
        # """应用hunk的修改
        
        # 保持正确的缩进和换行格式
        # """
        # if position == -1:
        #     return file_lines
            
        # # 创建新的行列表
        # new_lines = file_lines[:position]
        
        # # 获取原始缩进
        # base_indent = ''
        # if hunk['removed_lines']:
        #     # 从被删除的非空行中获取缩进
        #     for line in hunk['removed_lines']:
        #         if line.strip():  # 确保不是空行
        #             match = re.match(r'^[ \t]*', line)  # 只匹配空格和制表符，避免匹配到换行符
        #             if match:
        #                 base_indent = match.group(0)
        #                 break
        # elif position > 0:
        #     # 从前一个非空行获取缩进
        #     for i in range(position-1, -1, -1):
        #         if file_lines[i].strip():  # 确保不是空行
        #             match = re.match(r'^[ \t]*', file_lines[i])
        #             if match:
        #                 base_indent = match.group(0)
        #                 break

        # logger.debug(f"base indent length: {len(base_indent)}")
        
        # # 应用每一个新添加的行，保持正确的缩进
        # for added_line in hunk['added_lines']:
        #     if added_line.strip():  # 非空行
        #         # 获取新行的额外缩进（相对于基础缩进的额外空格）
        #         match = re.match(r'^[ \t]*', added_line)
        #         extra_indent = match.group(0) if match else ''
                
        #         # 保持原有的缩进结构
        #         final_line = base_indent + added_line[len(extra_indent):]
        #     else:
        #         # 空行保持原样
        #         final_line = added_line
                
        #     # 确保行末有换行符
        #     if not final_line.endswith('\n'):
        #         final_line += '\n'
        #     new_lines.append(final_line)
            
        #     # # 在某些语句后添加空行
        #     # if added_line.strip().endswith(('end', '}')):
        #     #     new_lines.append('\n')
    
        # # 添加剩余的行
        # new_lines.extend(file_lines[position + len(hunk['removed_lines']):])
        
        # return new_lines

        # if position == -1:
        #     return file_lines
            
        # # 创建新的行列表
        # new_lines = file_lines[:position]
        
        # # 直接使用添加的行，只处理换行符
        # for added_line in hunk['added_lines']:
        #     # 确保行末有换行符
        #     if not added_line.endswith('\n'):
        #         added_line += '\n'
        #     new_lines.append(added_line)
            
        #     # # 在某些语句后添加空行
        #     # if added_line.strip().endswith(('end', '}')):
        #     #     new_lines.append('\n')
        
        # # 添加剩余的行
        # new_lines.extend(file_lines[position + len(hunk['removed_lines']):])
        
        # return new_lines

        # """应用hunk的修改"""
        # if position == -1:
        #     return file_lines
            
        # new_lines = file_lines[:position]  # 保留修改位置之前的行
        
        # # 如果只有一个删除行和一个添加行，可能是行内修改
        # if (len(hunk['removed_lines']) == 1 and len(hunk['added_lines']) == 1 and
        #     hunk['removed_lines'][0].split('(')[0] == hunk['added_lines'][0].split('(')[0]):
        #     # 这是行内修改的情况
        #     new_lines.append(hunk['added_lines'][0] + '\n')
        #     new_lines.extend(file_lines[position + 1:])
        # else:
        #     # 添加新的行
        #     for added_line in hunk['added_lines']:
        #         new_lines.append(added_line + '\n')
            
        #     # 跳过被删除的行
        #     skip_lines = len(hunk['removed_lines'])
        #     new_lines.extend(file_lines[position + skip_lines:])
        
        # return new_lines

        # """应用hunk的修改"""
        # if position == -1:
        #     return file_lines
        
        # new_lines = file_lines[:position]
        
        # # 按序应用修改
        # for change_type, content in hunk['changes']:
        #     # 处理空行
        #     if content == '' and change_type == 'add':
        #         # 只有当前一行不是空行时才添加空行
        #         if new_lines and new_lines[-1].strip():
        #             new_lines.append('\n')
        #         continue
                
        #     if change_type in ('keep', 'add'):
        #         # 避免添加重复行
        #         if not new_lines or new_lines[-1].rstrip() != content:
        #             new_lines.append(content + '\n')

        
        # # 计算要跳过的行数（被删除的行和保持的行）
        # skip_count = len([c for c in hunk['changes'] if c[0] in ('remove', 'keep')])
        
        # # 添加剩余的行
        # remaining_lines = file_lines[position + skip_count:]
        # if remaining_lines and remaining_lines[0].strip() and new_lines[-1].strip():
        #     new_lines.append('\n')  # 在不同块之间添加空行
        # new_lines.extend(remaining_lines)
        
        # return new_lines

        # """应用hunk的修改"""
        # if position == -1:
        #     return file_lines
        
        # new_lines = file_lines[:position]
        
        # # 获取修改序列
        # changes = hunk['changes']
        
        # # # 检查是否需要在修改块开始前添加空行
        # # if (changes and changes[0][0] == 'add' and 
        # #     new_lines and new_lines[-1].strip() and 
        # #     not any(c[0] == 'remove' for c in changes[:1])):
        # #     new_lines.append('\n')
        
        # last_line_was_empty = False
        # for i, (change_type, content) in enumerate(changes):
        #     if change_type == 'add':
        #         if content == '':
        #             if not last_line_was_empty:
        #                 new_lines.append('\n')
        #                 last_line_was_empty = True
        #         else:
        #             new_lines.append(content + '\n')
        #             last_line_was_empty = False
        #     elif change_type == 'keep':
        #         if not (new_lines and new_lines[-1].rstrip() == content):
        #             new_lines.append(content + '\n')
        #             last_line_was_empty = False
        
        # # 计算要跳过的行数
        # skip_count = len([c for c in changes if c[0] in ('remove', 'keep')])
        
        # # 添加剩余的行
        # remaining_lines = file_lines[position + skip_count:]
        
        # # # 检查是否需要在修改块结束后添加空行
        # # if (changes and changes[-1][0] == 'add' and 
        # #     not changes[-1][1] == '' and  # 最后一个添加的不是空行
        # #     remaining_lines and remaining_lines[0].strip()):
        # #     new_lines.append('\n')
        
        # new_lines.extend(remaining_lines)
        
        # return new_lines
        if position == -1:
            return file_lines
        
        new_lines = file_lines[:position]
        current_pos = position
        
        # 应用修改
        i = 0
        while i < len(hunk['lines']):
            line_type, content = hunk['lines'][i]
            
            if line_type == 'remove':
                # 删除行：跳过原文件中的对应行
                current_pos += 1
            elif line_type == 'add':
                # 添加行：插入新内容
                new_lines.append(content + '\n')
            elif line_type == 'context':
                # 上下文行：保持原样
                if current_pos < len(file_lines):
                    new_lines.append(file_lines[current_pos])
                    current_pos += 1
            
            i += 1
        
        # 添加剩余的行
        new_lines.extend(file_lines[current_pos:])
        return new_lines
        

    def validate_modification(self, original_lines, modified_lines):
        """
        验证修改的合理性
        
        Args:
            original_lines: 原始文件的行列表
            modified_lines: 修改后的行列表
            
        Returns:
            bool: 修改是否合理
        """
        try:
            # 1. 基本检查
            if not modified_lines:
                logger.error("修改后的文件为空")
                return False
            
            # 2. 检查修改幅度
            if len(modified_lines) < len(original_lines) * 0.5 or \
               len(modified_lines) > len(original_lines) * 1.5:
                logger.warning("文件大小变化过大")
                return False
            
            # 3. 括号匹配检查
            if not self._check_brackets(modified_lines):
                logger.error("括号匹配错误")
                return False
            
            # 4. 缩进一致性检查
            if not self._check_indentation(modified_lines):
                logger.error("缩进不一致")
                return False
            
            # 5. 关键结构检查
            if not self._check_key_structures(original_lines, modified_lines):
                logger.error("关键结构被破坏")
                return False
            
            # # 6. 语言特定检查
            # if not self._check_language_specific(modified_lines):
            #     logger.error("语言特定规则验证失败")
            #     return False
            
            return True
        
        except Exception as e:
            logger.error(f"验证过程出错: {str(e)}")
            return False
        
    def _check_brackets(self, lines: List[str]) -> bool:
        """检查括号匹配"""
        stack = []
        brackets = {')': '(', '}': '{', ']': '['}
        
        for line in lines:
            for char in line:
                if char in '({[':
                    stack.append(char)
                elif char in ')}]':
                    if not stack or stack.pop() != brackets[char]:
                        return False
                    
        return len(stack) == 0

    def _check_indentation(self, lines: List[str]) -> bool:
        """检查缩进一致性"""
        prev_indent = 0
        for line in lines:
            if not line.strip():  # 跳过空行
                continue
            
            # 计算当前行的缩进
            current_indent = len(line) - len(line.lstrip())
            
            # 缩进变化不应过大
            if abs(current_indent - prev_indent) > 8:  # 允许最大缩进变化
                return False
            
            prev_indent = current_indent
        return True

    def _check_key_structures(self, original_lines: List[str], modified_lines: List[str]) -> bool:
        """检查关键结构完整性"""
        # 提取关键标识符（函数名、类名等）
        def extract_identifiers(lines):
            identifiers = set()
            # 简单的函数/类定义模式
            patterns = [
                r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
                r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:\(]'
            ]
            for line in lines:
                for pattern in patterns:
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        identifiers.add(match.group(1))
            return identifiers
        
        original_ids = extract_identifiers(original_lines)
        modified_ids = extract_identifiers(modified_lines)
        
        # 检查重要标识符是否保留
        important_ids_preserved = all(id_ in modified_ids 
                                    for id_ in original_ids 
                                    if not id_.startswith('_'))
        
        # 检查修改是否引入了过多的新标识符
        new_ids = modified_ids - original_ids
        if len(new_ids) > len(original_ids) * 0.3:  # 允许30%的新标识符
            return False
        
        return important_ids_preserved

    def _check_language_specific(self, lines: List[str]) -> bool:
        """语言特定的检查"""
        # 这里可以根据文件扩展名添加特定语言的检查
        # 例如，对于Python文件：
        
        in_function = False
        in_class = False
        
        for line in lines:
            stripped_line = line.strip()
            
            # 检查基本语法结构
            if stripped_line.startswith('def '):
                in_function = True
            elif stripped_line.startswith('class '):
                in_class = True
            elif stripped_line and not line[0].isspace():  # 非空行且无缩进
                in_function = False
                in_class = False
            
            # 检查基本语法错误
            if ':' in stripped_line:
                if stripped_line.count(':') > 1 and \
                   not any(quote in stripped_line for quote in ['"', "'"]):
                    return False
                
            # 检查缩进一致性
            if in_function or in_class:
                if stripped_line and not line[0].isspace():
                    return False
                
        return True

    def generate_adapted_file(self, llm_response_path, source_dir, output_dir):
        """
        将 LLM 生成的 patch 应用到旧版本的源文件
        
        Args:
            llm_response_path: LLM 生成的patch内容路径
            source_dir: 源文件目录（旧版本）
            output_dir: 输出目录
        """
        # read_text() 函数会使用html转义符，需要解码
        llm_response = Path(llm_response_path).read_text()
        # 解码HTML转义字符
        llm_response = html.unescape(llm_response)
        
        logger.info(f"the first diff_content:\n{llm_response}")
        
        # 解析patch，按文件分组
        current_file = None
        current_diff = []
        files_to_patch = {}
        
        # 解析git format-patch格式的输出
        for line in llm_response.splitlines():
            if line.startswith('diff --git'):
                if current_file and current_diff:
                    files_to_patch[current_file] = '\n'.join(current_diff)
                # 从 diff --git a/path/to/file b/path/to/file 提取文件路径
                current_file = line.split(' ')[-1][2:]  # 取 b/path/to/file 并去掉 b/
                current_diff = []
                continue
            if line.startswith('index '):
                continue
            if line.startswith('--- ') or line.startswith('+++ '):
                continue
            if current_file:
                current_diff.append(line)
        
        # 添加最后一个文件的diff
        if current_file and current_diff:
            files_to_patch[current_file] = '\n'.join(current_diff)
        
        # 创建输出目录
        output_dir = Path(output_dir)
        if not output_dir.exists():
            output_dir.mkdir(parents=True)
        
        # 处理每个文件
        for file_path, diff_content in files_to_patch.items():
            source_file = Path(source_dir) / file_path
            target_file = output_dir / file_path
            logger.info(f"the diff_content:\n{diff_content}")
            
            if not source_file.exists():
                logger.error(f"源文件不存在: {source_file}, 已跳过")
                continue
            
            # 确保目标目录存在
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                # 读取源文件内容
                with open(source_file, 'r', encoding='utf-8') as f:
                    source_lines = f.readlines()
                
                # 解析patch中的hunks
                hunks_text = re.split(r'(?=@@ -\d+,\d+ \+\d+,\d+ @@)', diff_content)
                hunks_text = [h for h in hunks_text if h.strip()]
                
                # 处理每个hunk
                modified_lines = source_lines[:]
                for hunk_text in hunks_text:
                    try:
                        logger.info(f"hunk_text is {hunk_text}")
                                                    
                        # 解析hunk，现在返回的是一个列表
                        hunks = self.parse_hunk(hunk_text)
                        
                        # 处理每个子hunk
                        for hunk in hunks:
                            logger.info(f"hunk is {hunk}")
                            # 找到最佳匹配位置
                            position = self.find_best_match_position(modified_lines, hunk)
                            logger.info(f"position is {position}")
                            
                            if position == -1:
                                logger.warning(f"在文件中未找到hunk的合适位置:\n{hunk}")
                                continue
                            
                            # 应用修改
                            modified_lines = self.apply_hunk(modified_lines, position, hunk)
                            
                            # # 验证修改
                            # if not self.validate_modification(source_lines, modified_lines):
                            #     logger.warning("修改验证失败")
                            #     continue
                                
                    except Exception as e:
                        logger.error(f"处理hunk时出错: {str(e)}\n{hunk_text}")
                        continue
                
                # 写入修改后的文件
                with open(target_file, 'w', encoding='utf-8') as f:
                    # logger.info("success.\n")
                    f.writelines(modified_lines)
                logger.info(f"成功应用修改到文件: {file_path}")
                
            except Exception as e:
                logger.error(f"处理文件 {file_path} 时出错: {str(e)}")
                continue
