#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys
import argparse
import shutil  # 需要在文件开头添加这个导入

def main():
    # 命令行参数解析
    parser = argparse.ArgumentParser(description='处理区域分析JSON文件并执行数据拷贝和直方图分析')
    parser.add_argument('json_file', help='region_analysis.json文件路径')
    parser.add_argument('-s', '--source-dirs', nargs='+', required=True,
                        help='源目录列表，例如: -s dir1 dir2 dir3')
    parser.add_argument('-d', '--dT', type=float, default=0.005e6,
                        help='频率宽度的一半，单位Hz (默认: 0.005e6 = 5000 Hz)')
    parser.add_argument('--copy-script', default='../../copy_files.py',
                        help='copy_files.py脚本路径 (默认: ../copy_files.py)')
    parser.add_argument('--sum-script', default='../../sum_root_hist.py',
                        help='sum_root_hist.py脚本路径 (默认: ../sum_root_hist.py)')
    
    # sum_root_hist.py 的参数
    parser.add_argument('--dir', default='./injection_spectrum',
                        help='输入数据目录 (默认: ./injection_spectrum)')
    parser.add_argument('--h2', default='h2d',
                        help='h2参数名称 (默认: h2d)')
    parser.add_argument('--h1', default='h_proj',
                        help='h1参数名称 (默认: h_proj)')
    parser.add_argument('-o', '--output', default='sum.root',
                        help='输出root文件名 (默认: sum.root)')
    parser.add_argument('--plot_dir', default='sum',
                        help='绘图输出目录 (默认: sum)')
    parser.add_argument('--t_min', type=float, default=0.0,
                        help='t_min参数 (默认: 0)')
    parser.add_argument('--t_max', type=float, default=3.0,
                        help='t_max参数 (默认: 3.0)')
    parser.add_argument('--z_min', type=float, default=-0.0001,
                        help='z_min参数 (默认: -0.0001)')
    parser.add_argument('--z_max', type=float, default=0.005,
                        help='z_max参数 (默认: 0.005)')
    parser.add_argument('--freq_width_tgt', type=float, default=800,
                        help='freq_width_tgt参数 (默认: 800)')
    parser.add_argument('--amp_threshold', type=float, default=0.02,
                        help='amp_threshold参数 (默认: 0.02)')
    parser.add_argument('--no-logz', action='store_true', default=False,
                        help='禁用logz (默认: False)')
    parser.add_argument('--no-correct-frequency', action='store_true', default=False,
                        help='禁用频率校正 (默认: False)')
    
    # 添加开关参数
    parser.add_argument('--skip-copy', action='store_true',
                        help='跳过执行 copy_files.py 命令')
    parser.add_argument('--skip-sum', action='store_true',
                        help='跳过读取 freq_mean 并执行 sum_root_hist.py')
    
    # 添加控制处理区域数目的参数
    parser.add_argument('-n', '--num-regions', type=int, default=None,
                        help='处理的区域数目 (默认: 处理所有区域)')
    
    args = parser.parse_args()
    
    json_file = args.json_file
    source_dirs = args.source_dirs
    dT = args.dT
    copy_script = args.copy_script
    sum_script = args.sum_script
    skip_copy = args.skip_copy
    skip_sum = args.skip_sum
    num_regions = args.num_regions
    
    # sum_root_hist.py 的参数
    sum_dir = args.dir
    h2 = args.h2
    h1 = args.h1
    output_root = args.output
    plot_dir_base = args.plot_dir
    t_min = args.t_min
    t_max = args.t_max
    z_min = args.z_min
    z_max = args.z_max
    freq_width_tgt = args.freq_width_tgt
    amp_threshold = args.amp_threshold
    no_logz = args.no_logz
    no_correct_frequency = args.no_correct_frequency
    
    # 1. 检查JSON文件是否存在
    if not os.path.exists(json_file):
        print(f"错误: 文件 {json_file} 不存在")
        sys.exit(1)
    
    # 2. 读取JSON文件
    with open(json_file, 'r', encoding='utf-8') as f:
        all_regions = json.load(f)
    
    # 根据参数限制处理的区域数目
    if num_regions is not None:
        regions = all_regions[:num_regions]
        print(f"总共 {len(all_regions)} 个区域，将处理前 {len(regions)} 个区域")
    else:
        regions = all_regions
        print(f"总共 {len(regions)} 个区域，将处理所有区域")
    
    print(f"源目录列表: {source_dirs}")
    print(f"频率宽度参数 dT = {dT} Hz ({dT/1e6:.6f} MHz)")
    print(f"执行拷贝: {'否' if skip_copy else '是'}")
    print(f"执行求和: {'否' if skip_sum else '是'}")
    print(f"sum_root_hist.py 参数:")
    print(f"  --dir: {sum_dir}")
    print(f"  --h2: {h2}")
    print(f"  --h1: {h1}")
    print(f"  -o: {output_root}")
    print(f"  --plot_dir: {plot_dir_base}")
    print(f"  --t_min: {t_min}")
    print(f"  --t_max: {t_max}")
    print(f"  --z_min: {z_min}")
    print(f"  --z_max: {z_max}")
    print(f"  --freq_width_tgt: {freq_width_tgt}")
    print(f"  --amp_threshold: {amp_threshold}")
    print(f"  --no-logz: {no_logz}")
    print(f"  --no-correct-frequency: {no_correct_frequency}")
    print("-" * 60)
    
    # 3. 处理每个区域
    for idx, region in enumerate(regions, 1):
        # 获取原始的 region_name 和 region_index
        original_name = region['name']
        region_index = region['region_index']
        
        # 重新组合 region_name 为 "region_{region_index}_{original_name}"
        region_name = f"region_{region_index}_{original_name}"
        
        # 去掉名称中的"+"
        clean_name = region_name.replace('+', '')
        
        print(f"\n处理区域 {idx}/{len(regions)}: {original_name} -> {region_name} -> {clean_name}")
        
        # 创建文件夹（删除旧的）
        folder_path = os.path.join(os.getcwd(), "analysis_results", clean_name)
        if os.path.exists(folder_path):
            print(f"  检测到已存在的文件夹: {folder_path}")
            shutil.rmtree(folder_path)  # 删除整个文件夹及其内容
            print(f"  已删除旧的文件夹")
        os.makedirs(folder_path)  # 创建新文件夹
        print(f"  创建新文件夹: {folder_path}")        
        
        # 4. 处理 selected_lines，提取最后一列的文件名
        selected_lines = region['selected_lines']
        if selected_lines:
            # 提取最后一列（文件名）
            filenames = []
            for line in selected_lines:
                if isinstance(line, (list, tuple)):
                    # 如果是列表，取最后一个元素作为文件名
                    filename = str(line[-1])
                elif isinstance(line, str):
                    # 如果是字符串，按空格或制表符分割，取最后一列
                    parts = line.strip().split()
                    filename = parts[-1] if parts else line
                else:
                    # 如果是其他类型，直接转换为字符串
                    filename = str(line)
                
                filenames.append(filename)
            
            # 写入 filelist.txt（每个文件名一行）
            filelist_path = os.path.join(folder_path, 'filelist.txt')
            with open(filelist_path, 'w') as f:
                f.write('\n'.join(filenames))
            print(f"  写入 {len(filenames)} 个文件名到 {filelist_path}")
            # 显示前3个文件名作为示例
            for i, fname in enumerate(filenames[:3], 1):
                print(f"    示例 {i}: {fname}")
            if len(filenames) > 3:
                print(f"    ... 共 {len(filenames)} 个")
            
            # 5. 执行 copy_files.py 命令（如果不跳过）
            if not skip_copy:
                data_dir = os.path.join(folder_path, args.dir)
                copy_cmd = [
                    'python', copy_script,
                    '-f', filelist_path,
                    '-d', data_dir
                ]
                
                # 添加所有 -s 参数
                for src_dir in source_dirs:
                    copy_cmd.extend(['-s', src_dir])
                
                print(f"  执行拷贝命令: {' '.join(copy_cmd)}")
                try:
                    result = subprocess.run(copy_cmd, cwd=folder_path, check=True)
                    print(f"  ✓ 拷贝完成")
                    if result.stdout:
                        print(f"    输出: {result.stdout[:200]}")
                except subprocess.CalledProcessError as e:
                    print(f"  ✗ 错误: 拷贝失败")
                    print(f"    错误输出: {e.stderr}")
                    if skip_sum:
                        # 如果也跳过求和，则继续下一个区域
                        continue
                    else:
                        # 如果不跳过求和，但拷贝失败，询问是否继续
                        print(f"    警告: 拷贝失败，但将继续执行求和步骤")
            else:
                print(f"  ⏭ 跳过拷贝步骤")
                # 即使跳过拷贝，也需要确保data目录存在（供后续求和使用）
                data_dir = os.path.join(folder_path, args.dir)
                os.makedirs(data_dir, exist_ok=True)
                print(f"  创建数据目录: {data_dir}")
        else:
            print(f"  警告: selected_lines 为空")
            if not skip_copy:
                print(f"  跳过拷贝步骤（因为没有文件名）")
        
        # 6. 读取 freq_mean 并执行 sum_root_hist.py（如果不跳过）
        if not skip_sum:
            freq_mean = region['freq_mean']
            
            # 计算频率参数
            freq_low = freq_mean * 1e6 - dT
            freq_high = freq_mean * 1e6 + dT
            freq_tgt = freq_mean * 1e6
            freq_lifetime = freq_mean * 1e6
            
            print(f"  频率参数:")
            print(f"    freq_mean = {freq_mean:.6f} MHz")
            print(f"    freq_low  = {freq_low:.3f} Hz  ({freq_low/1e6:.6f} MHz)")
            print(f"    freq_high = {freq_high:.3f} Hz ({freq_high/1e6:.6f} MHz)")
            print(f"    freq_tgt  = {freq_tgt:.3f} Hz  ({freq_tgt/1e6:.6f} MHz)")
            
            # 构建 sum_root_hist.py 命令（使用命令行参数）
            sum_cmd = [
                'python', sum_script,
                '--dir', sum_dir,
                '--h2', h2,
                '--h1', h1,
                '-o', output_root,
                '--plot_dir', plot_dir_base,
                '--t_min', str(t_min),
                '--t_max', str(t_max),
                '--z_min', str(z_min),
                '--z_max', str(z_max),
                '--freq_low', str(freq_low),
                '--freq_high', str(freq_high),
                '--freq_tgt', str(freq_tgt),
                '--freq_lifetime', str(freq_lifetime),
                '--freq_width_tgt', str(freq_width_tgt),
                '--amp_threshold', str(amp_threshold)
            ]
            
            # 添加可选的标志参数
            if no_logz:
                sum_cmd.append('--no-logz')
            if no_correct_frequency:
                sum_cmd.append('--no-correct-frequency')
            
            print(f"  执行求和命令: {' '.join(sum_cmd[:8])} ...")
            try:
                result = subprocess.run(sum_cmd, cwd=folder_path, check=True)
                print(f"  ✓ 直方图分析完成")
                if result.stdout:
                    print(f"    输出: {result.stdout[:200]}")
            except subprocess.CalledProcessError as e:
                print(f"  ✗ 错误: 直方图分析失败")
                print(f"    错误输出: {e.stderr}")
        else:
            print(f"  ⏭ 跳过求和步骤")
        
        print(f"  ✓ 完成区域: {region_name}")
        print("-" * 50)

if __name__ == "__main__":
    main()