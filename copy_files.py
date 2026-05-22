#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import os
import shutil
import glob
import argparse
import sys
from typing import List, Optional

def copy_files_by_prefix(
    filelist_path: str,
    source_dirs: List[str],
    dest_dir: str,
    verbose: bool = True
) -> int:
    """
    根据前缀列表从多个源目录复制匹配的文件到目标目录
    
    Parameters:
    -----------
    filelist_path : str
        包含文件名前缀的列表文件路径
    source_dirs : List[str]
        源目录列表，可以包含多个路径
    dest_dir : str
        目标目录路径
    verbose : bool
        是否打印详细信息
    
    Returns:
    --------
    int
        成功复制的文件数量
    """
    
    # 确保目标目录存在
    os.makedirs(dest_dir, exist_ok=True)
    
    # 存储已复制的文件（避免重复复制相同文件名）
    copied_files = set()
    copied_count = 0
    
    # 记录未找到的前缀
    not_found_prefixes = {}
    
    # 读取前缀列表
    prefixes = []
    try:
        with open(filelist_path, 'r', encoding='utf-8') as f:
            for line in f:
                prefix = line.strip()
                if prefix:
                    prefixes.append(prefix)
    except FileNotFoundError:
        print(f"❌ 错误: 找不到文件列表 {filelist_path}")
        return 0
    except Exception as e:
        print(f"❌ 读取文件列表失败: {e}")
        return 0
    
    if not prefixes:
        print(f"⚠️  警告: {filelist_path} 中没有有效的前缀")
        return 0
    
    # 先过滤出存在的源目录
    valid_source_dirs = []
    for source_dir in source_dirs:
        if os.path.exists(source_dir):
            valid_source_dirs.append(source_dir)
        else:
            if verbose:
                print(f"⚠️  源目录不存在，跳过: {source_dir}")
    
    if not valid_source_dirs:
        print(f"❌ 错误: 没有有效的源目录")
        return 0
    
    if verbose:
        print(f"📋 共读取 {len(prefixes)} 个前缀")
        print(f"📁 源目录: {', '.join(valid_source_dirs)}")
        print(f"📂 目标目录: {dest_dir}")
        print("-" * 60)
    
    # 先遍历每个前缀，再遍历每个源目录
    for prefix in prefixes:
        found_for_this_prefix = False
        found_files = []
        
        # 在每个源目录中查找匹配的文件
        for source_dir in valid_source_dirs:
            # 构造通配符模式：filename*
            pattern = os.path.join(source_dir, prefix + "*")
            
            # 查找所有匹配的文件
            matched_files = glob.glob(pattern)
            
            if matched_files:
                found_for_this_prefix = True
                for src_path in matched_files:
                    filename = os.path.basename(src_path)
                    found_files.append((src_path, filename, source_dir))
        
        # 如果没找到任何匹配的文件
        if not found_for_this_prefix:
            not_found_prefixes[prefix] = valid_source_dirs.copy()
            if verbose:
                print(f"  ❌ 未找到匹配文件: {prefix}* (在所有源目录中)")
            continue
        
        # 复制找到的文件（选择第一个找到的，或根据优先级选择）
        if verbose:
            if len(found_files) > 1:
                print(f"  🔍 前缀 '{prefix}' 找到 {len(found_files)} 个匹配文件:")
                for src_path, filename, source_dir in found_files:
                    print(f"      - {filename} (在 {source_dir})")
        
        # 复制文件（选择第一个找到的，避免重复）
        for src_path, filename, source_dir in found_files:
            # 避免重复复制相同文件名的文件
            if filename in copied_files:
                if verbose:
                    print(f"  ⏭️  跳过重复: {filename}")
                continue
            
            dst_path = os.path.join(dest_dir, filename)
            
            try:
                shutil.copy2(src_path, dst_path)
                if verbose:
                    if len(found_files) == 1:
                        print(f"  ✅ 已复制: {filename} (从 {source_dir})")
                    else:
                        print(f"      ✅ 已复制: {filename} (从 {source_dir})")
                copied_files.add(filename)
                copied_count += 1
            except Exception as e:
                print(f"  ❌ 复制失败 {filename}: {e}")
    
    # 输出未找到的前缀汇总（只在安静模式下也显示）
    if not_found_prefixes and not verbose:
        print(f"\n⚠️  以下 {len(not_found_prefixes)} 个前缀未在任何源目录中找到:")
        for prefix in list(not_found_prefixes.keys())[:10]:  # 最多显示10个
            print(f"    - {prefix}*")
        if len(not_found_prefixes) > 10:
            print(f"    ... 还有 {len(not_found_prefixes) - 10} 个")
    
    return copied_count

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='根据前缀列表从多个源目录复制文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基本用法（单个源目录）
  python script.py -f filelist.txt -s ../ROOT_Data_BGSub/ -d data
  
  # 多个源目录（空格分隔）
  python script.py -f filelist.txt -s ../dir1/ ../dir2/ ../dir3/ -d data
  
  # 多个源目录（多次使用-s）
  python script.py -f filelist.txt -s ../dir1/ -s ../dir2/ -s ../dir3/ -d data
  
  # 安静模式（不打印详细信息）
  python script.py -f filelist.txt -s ../ROOT_Data_BGSub/ -d data -q
        """
    )
    
    parser.add_argument(
        '-f', '--filelist',
        type=str,
        default='filelist.txt',
        help='包含文件名前缀的列表文件路径 (默认: filelist.txt)'
    )
    
    parser.add_argument(
        '-s', '--source-dirs',
        type=str,
        action='append',  # 支持多次使用 -s
        required=True,
        help='源目录路径，可以多次使用 -s 指定多个目录'
    )
    
    parser.add_argument(
        '-d', '--dest-dir',
        type=str,
        default='data',
        help='目标目录路径 (默认: data)'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='安静模式，不打印详细信息'
    )
    
    return parser.parse_args()

def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 处理源目录：展平列表（因为 action='append' 会产生嵌套列表）
    source_dirs = []
    for item in args.source_dirs:
        if isinstance(item, list):
            source_dirs.extend(item)
        else:
            source_dirs.append(item)
    
    # 去重（保持顺序）
    seen = set()
    source_dirs = [x for x in source_dirs if not (x in seen or seen.add(x))]
    
    if not source_dirs:
        print("❌ 错误: 请至少指定一个源目录")
        return 1
    
    # 执行复制操作
    copied_count = copy_files_by_prefix(
        filelist_path=args.filelist,
        source_dirs=source_dirs,
        dest_dir=args.dest_dir,
        verbose=not args.quiet
    )
    
    # 打印总结
    print("\n" + "=" * 60)
    print(f"📊 复制完成！共复制 {copied_count} 个文件到 {args.dest_dir} 目录。")
    
    if copied_count == 0:
        print("⚠️  没有文件被复制，请检查：")
        print("   1. filelist.txt 中的前缀是否正确")
        print("   2. 源目录路径是否正确")
        print("   3. 源目录中是否存在匹配的文件")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())