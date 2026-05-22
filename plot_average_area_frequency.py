import ROOT
import numpy as np
import sys
import argparse
import os
import json
ROOT.gStyle.SetOptTitle(0)

def read_peaks_data_with_full_lines(filename):
    """
    读取峰值数据文件，提取频率、每frame面积和完整的原始行
    
    Parameters:
    -----------
    filename : str
        数据文件路径
    
    Returns:
    --------
    frequencies : np.ndarray
        频率数组
    areas_per_frame : np.ndarray
        每frame面积数组
    full_lines : list
        完整的原始数据行列表
    """
    frequencies = []
    areas_per_frame = []
    full_lines = []
    
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            
            # 查找数据开始的行（跳过标题行和分隔线）
            data_start_index = 0
            for i, line in enumerate(lines):
                # 如果行以数字开头，说明是数据行
                if line.strip() and line.strip()[0].isdigit():
                    data_start_index = i
                    break
            
            # 从数据开始行读取
            for line in lines[data_start_index:]:
                line = line.strip()
                if not line:
                    continue
                
                # 使用split()分割空白字符
                parts = line.split()
                
                # 新格式列索引：
                # 总序号(0), 峰序号(1), 频率[MHz](2), 峰高(3), FWHM[MHz](4), 
                # start[s](5), end[s](6), 寿命[s](7), 寿命[frame](8), 面积(9), 每frame面积(10), 文件名(11...)
                if len(parts) >= 11:
                    try:
                        # 频率在第3列（索引2）
                        freq = float(parts[2])
                        # 每frame面积在第11列（索引10）
                        area_per_frame = float(parts[10])
                        # 文件名可能包含空格，从第12列开始到结束
                        filename_parts = parts[11:] if len(parts) > 11 else []
                        full_line = line  # 保存完整的原始行
                        
                        frequencies.append(freq)
                        areas_per_frame.append(area_per_frame)
                        full_lines.append(full_line)
                    except (ValueError, IndexError) as e:
                        print(f"警告: 跳过无法解析的行: {line[:50]}... 错误: {e}")
                        continue
        
        if len(frequencies) == 0:
            raise ValueError("未能从文件中读取到有效数据")
            
    except FileNotFoundError:
        raise FileNotFoundError(f"错误: 找不到文件 '{filename}'")
    except Exception as e:
        raise Exception(f"读取文件时出错: {e}")
    
    return np.array(frequencies), np.array(areas_per_frame), full_lines

def merge_multiple_peaks_files(filenames):
    """
    合并多个峰值数据文件
    
    Parameters:
    -----------
    filenames : list
        数据文件路径列表
    
    Returns:
    --------
    frequencies : np.ndarray
        合并后的频率数组
    areas_per_bin : np.ndarray
        合并后的每bin面积数组
    full_lines : list
        合并后的完整原始行列表
    """
    all_frequencies = []
    all_areas = []
    all_lines = []
    
    for filename in filenames:
        print(f"正在读取: {filename}")
        freqs, areas, lines = read_peaks_data_with_full_lines(filename)
        all_frequencies.extend(freqs)
        all_areas.extend(areas)
        all_lines.extend(lines)
        print(f"  添加了 {len(freqs)} 个数据点")
    
    print(f"\n总计: {len(all_frequencies)} 个数据点")
    
    return (np.array(all_frequencies), 
            np.array(all_areas), 
            all_lines)
    
def read_simulation_results(filename):
    """
    读取simulation_result.out文件，提取频率和yield信息
    
    Parameters:
    -----------
    filename : str
        仿真结果文件路径
    
    Returns:
    --------
    frequencies : np.ndarray
        频率数组 (单位: Hz)
    yields : np.ndarray
        yield数组 (单位: pps)
    ion_names : list
        离子名称列表
    """
    frequencies = []
    yields = []
    ion_names = []
    
    try:
        with open(filename, 'r') as f:
            lines = f.readlines()
            
            # 跳过第一行标题
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                
                # 使用split()分割空白字符
                parts = line.split()
                
                # 格式: ion, frequency[Hz], yield[pps], m/q[u], mass[MeV/c²]
                if len(parts) >= 3:
                    try:
                        ion_name = parts[0]
                        freq_hz = float(parts[1])
                        yield_pps = float(parts[2])
                        frequencies.append(freq_hz)
                        yields.append(yield_pps)
                        ion_names.append(ion_name)
                    except (ValueError, IndexError) as e:
                        print(f"警告: 跳过无法解析的行: {line[:50]}... 错误: {e}")
                        continue
        
        if len(frequencies) == 0:
            print("警告: 未能从simulation_result.out中读取到有效数据")
            
    except FileNotFoundError:
        print(f"警告: 找不到文件 '{filename}'，将跳过谐波线绘制")
    except Exception as e:
        print(f"警告: 读取simulation_result.out时出错: {e}")
    
    return np.array(frequencies), np.array(yields), ion_names


def add_harmonic_lines_simple(canvas, graph, sim_frequencies, sim_yields, harmonic_min, harmonic_max, ion_names, x_min=None, x_max=None, yield_threshold=None):
    """
    添加谐波线，可以设置yield阈值，只绘制yield大于阈值的线
    
    Parameters:
    -----------
    canvas : ROOT.TCanvas
        ROOT画布对象
    graph : ROOT.TGraph
        图形对象
    sim_frequencies : np.ndarray
        仿真频率数组 (单位: Hz)
    sim_yields : np.ndarray
        仿真yield数组 (单位: pps)
    harmonic_min : int
        最小谐波数
    harmonic_max : int
        最大谐波数
    ion_names : list
        离子名称列表
    x_min : float, optional
        X轴最小值 (MHz)
    x_max : float, optional
        X轴最大值 (MHz)
    yield_threshold : float, optional
        Yield阈值 (pps)，只有yield > 阈值的线才会被绘制
    """
    if len(sim_frequencies) == 0:
        return []
    
    # 获取当前图形的x轴范围（优先使用传入的参数，否则从graph获取）
    if x_min is None:
        x_min = graph.GetXaxis().GetXmin()
    if x_max is None:
        x_max = graph.GetXaxis().GetXmax()
    
    y_min = graph.GetHistogram().GetMinimum()
    y_max = graph.GetHistogram().GetMaximum()
    
    harmonic_numbers = list(range(harmonic_min, harmonic_max + 1))
    colors = [ROOT.kRed, ROOT.kBlue, ROOT.kGreen+2, ROOT.kMagenta, ROOT.kOrange+1, ROOT.kCyan+2]
    
    lines = []
    canvas.cd()
    # 预先计算所有谐波频率并过滤
    total_candidates = 0
    drawn_count = 0
    filtered_by_threshold = 0
    simulation_lines = []
    for idx, harmonic in enumerate(harmonic_numbers):
        harmonic_freqs_mhz = sim_frequencies * harmonic / 1e6
        
        for i, freq_mhz in enumerate(harmonic_freqs_mhz):
            total_candidates += 1
            
            # 检查yield阈值
            if yield_threshold is not None and sim_yields[i] <= yield_threshold:
                filtered_by_threshold += 1
                continue
            
            if x_min <= freq_mhz <= x_max:
                drawn_count += 1
                line = ROOT.TLine(freq_mhz, y_min, freq_mhz, y_max)
                color = colors[idx % len(colors)]
                line.SetLineColor(color)
                line.SetLineWidth(2)
                #line.DrawClone()
                #lines.append(line)
                
                # 添加标签，包含离子名称、谐波数和yield值
                label = ROOT.TLatex()
                label.SetTextSize(0.018)  # 稍微减小字体以容纳更多信息
                label.SetTextColor(color)
                label.SetTextAngle(90)
                
                # 格式化yield值（使用科学计数法）
                yield_str = f"{sim_yields[i]:.2e}"
                
                # 创建标签文本
                label_text = f"{ion_names[i]} (n={harmonic}, y={yield_str} pps)"
                #label.DrawLatex(freq_mhz, y_max*1, label_text)
                simulation_lines.append({
                'frequency': freq_mhz,
                'line': line,
                'label': label,
                'ion_name': ion_names[i],
                'harmonic': harmonic,
                'yield_value': sim_yields[i],
                'color': color
            })
    # 打印统计信息
    print(f"谐波线绘制统计:")
    print(f"  - 总候选频率: {total_candidates}")
    if yield_threshold is not None:
        print(f"  - Yield阈值: {yield_threshold:.2e} pps")
        print(f"  - 低于阈值被过滤: {filtered_by_threshold}")
    print(f"  - 在x轴范围内绘制: {drawn_count}")
    
    canvas.Update()
    return simulation_lines


def create_and_plot_graph(frequencies, areas_per_frame, title=None, 
                         x_min=None, x_max=None, y_min=None, y_max=None):
    """
    创建并绘制TGraph
    
    Parameters:
    -----------
    frequencies : np.ndarray
        频率数组
    areas_per_frame : np.ndarray
        每frame面积数组
    title : str, optional
        图形标题
    x_min : float, optional
        X轴最小值
    x_max : float, optional
        X轴最大值
    y_min : float, optional
        Y轴最小值
    y_max : float, optional
        Y轴最大值
    """
    n_points = len(frequencies)
    
    # 创建TGraph
    graph = ROOT.TGraph(n_points, frequencies, areas_per_frame)
    
    # 设置图形标题和轴标签
    if title:
        graph.SetTitle(title)
    else:
        graph.SetTitle("Frequency Spectrum;Frequency (MHz);Area per Frame")
    
    # 设置图形样式
    graph.SetMarkerStyle(7)      # 实心圆点
    graph.SetMarkerSize(1)
    graph.SetMarkerColor(ROOT.kBlue)
    graph.SetLineColor(ROOT.kBlue - 3)
    graph.SetLineWidth(1)
    graph.SetLineStyle(1)
    
    # 创建Canvas
    canvas = ROOT.TCanvas("canvas", "Peak Analysis", 0,0,1900,1095)
    
    canvas.SetRightMargin(0.03882476)
    canvas.SetTopMargin(0.2908067)
    canvas.SetBottomMargin(0.120075)
    canvas.SetGrid(1, 1)  # 打开网格
    
    graph.Draw("AP")
    
    # 设置轴标签和刻度字体大小
    graph.GetXaxis().SetTitle("Frequency (MHz)")
    graph.GetXaxis().CenterTitle(1)
    graph.GetXaxis().SetDecimals()
    graph.GetXaxis().SetLabelFont(42)
    graph.GetXaxis().SetLabelOffset(0.011)
    graph.GetXaxis().SetLabelSize(0.04)
    graph.GetXaxis().SetTitleSize(0.04)
    graph.GetXaxis().SetTitleOffset(1)
    graph.GetXaxis().SetTitleFont(42)
    graph.GetYaxis().SetTitle("Area per Frame")
    graph.GetYaxis().CenterTitle(1)
    graph.GetYaxis().SetDecimals()
    graph.GetYaxis().SetLabelFont(42)
    graph.GetYaxis().SetLabelOffset(0.006)
    graph.GetYaxis().SetTitleSize(0.04)
    graph.GetYaxis().SetTitleFont(42)
    
    # 设置轴范围（如果提供了参数）
    if x_min is not None and x_max is not None:
        graph.GetXaxis().SetRangeUser(x_min, x_max)
        print(f"设置X轴范围: [{x_min}, {x_max}] MHz")
    elif x_min is not None:
        current_max = graph.GetXaxis().GetXmax()
        graph.GetXaxis().SetRangeUser(x_min, current_max)
        print(f"设置X轴最小值: {x_min} MHz")
    elif x_max is not None:
        current_min = graph.GetXaxis().GetXmin()
        graph.GetXaxis().SetRangeUser(current_min, x_max)
        print(f"设置X轴最大值: {x_max} MHz")
    
    if y_min is not None and y_max is not None:
        graph.SetMinimum(y_min)
        graph.SetMaximum(y_max)
        print(f"设置Y轴范围: [{y_min}, {y_max}]")
    elif y_min is not None:
        graph.SetMinimum(y_min)
        print(f"设置Y轴最小值: {y_min}")
    elif y_max is not None:
        graph.SetMaximum(y_max)
        print(f"设置Y轴最大值: {y_max}")

    # 更新画布
    canvas.Update()
    
    return canvas, graph


def parse_region_string(region_str):
    """
    解析区域字符串，支持3种格式：
    1. "x_min,x_max" - 只有X范围
    2. "x_min,x_max,y_min,y_max" - X和Y范围
    3. "x_min,x_max,y_min,y_max,region_name" - X、Y范围和区域名称
    
    Parameters:
    -----------
    region_str : str
        区域字符串
    
    Returns:
    --------
    dict : 包含区域信息的字典
    """
    parts = region_str.split(',')
    
    if len(parts) == 2:
        # 只有X范围
        x_min, x_max = map(float, parts[:2])
        return {
            'x_min': x_min,
            'x_max': x_max,
            'y_min': None,
            'y_max': None,
            'name': f"Region"
        }
    elif len(parts) == 4:
        # X和Y范围，无名称
        x_min, x_max, y_min, y_max = map(float, parts[:4])
        return {
            'x_min': x_min,
            'x_max': x_max,
            'y_min': y_min,
            'y_max': y_max,
            'name': f"Region"
        }
    elif len(parts) == 5:
        # X、Y范围和名称
        x_min, x_max, y_min, y_max = map(float, parts[:4])
        name = parts[4]
        return {
            'x_min': x_min,
            'x_max': x_max,
            'y_min': y_min,
            'y_max': y_max,
            'name': name
        }
    else:
        raise ValueError(f"无效的区域格式: '{region_str}'。支持格式: 'x_min,x_max', 'x_min,x_max,y_min,y_max', 或 'x_min,x_max,y_min,y_max,region_name'")


def analyze_region(frequencies, areas_per_frame, full_lines, x_min, x_max, y_min=None, y_max=None, region_name=None):
    """
    分析指定区域内的数据点
    
    Parameters:
    -----------
    frequencies : np.ndarray
        频率数组
    areas_per_frame : np.ndarray
        每frame面积数组
    full_lines : list
        完整的原始数据行列表
    x_min : float
        X轴最小值
    x_max : float
        X轴最大值
    y_min : float, optional
        Y轴最小值
    y_max : float, optional
        Y轴最大值
    region_name : str, optional
        区域名称
    
    Returns:
    --------
    dict : 包含区域分析结果的字典
    """
    # 创建掩码：在x范围内
    mask = (frequencies >= x_min) & (frequencies <= x_max)
    
    # 如果指定了y范围，进一步过滤
    if y_min is not None:
        mask = mask & (areas_per_frame >= y_min)
    if y_max is not None:
        mask = mask & (areas_per_frame <= y_max)
    
    # 获取满足条件的点
    selected_freqs = frequencies[mask]
    selected_areas = areas_per_frame[mask]
    selected_lines = [full_lines[i] for i in range(len(full_lines)) if mask[i]]
    n_points = len(selected_freqs)
    
    if n_points > 0:
        freq_mean = np.mean(selected_freqs)
        freq_std = np.std(selected_freqs)
        area_mean = np.mean(selected_areas)
        area_std = np.std(selected_areas)
        area_sum = np.sum(selected_areas)
    else:
        freq_mean = freq_std = area_mean = area_std = area_sum = 0.0
    
    return {
        'name': region_name if region_name else f"Region",
        'x_min': x_min,
        'x_max': x_max,
        'y_min': y_min if y_min is not None else -np.inf,
        'y_max': y_max if y_max is not None else np.inf,
        'n_points': n_points,
        'freq_mean': freq_mean,
        'freq_std': freq_std,
        'area_mean': area_mean,
        'area_std': area_std,
        'area_sum': area_sum,
        'selected_frequencies': selected_freqs.tolist(),
        'selected_areas': selected_areas.tolist(),
        'selected_lines': selected_lines  # 保存完整的原始行
    }


def draw_region_boxes(canvas, graph, regions, simulation_lines, save_images=True):
    """
    在图形上绘制区域框
    
    Parameters:
    -----------
    canvas : ROOT.TCanvas
        ROOT画布对象
    graph : ROOT.TGraph
        图形对象
    regions : list
        区域列表，每个区域是包含x_min, x_max, y_min, y_max, name的字典
    """
    
    boxes = []
    boxe_labels = []
    # 定义颜色列表
    colors = [ROOT.kRed, ROOT.kGreen+2, ROOT.kBlue, ROOT.kMagenta, ROOT.kOrange+1, ROOT.kCyan+2]
    
    for i, region in enumerate(regions):
        canvas.cd()
        primitives = canvas.GetListOfPrimitives()
        to_delete = []
        for prim in primitives:
            # 排除graph对象，只删除TLine和TLatex
            if prim != graph and (isinstance(prim, ROOT.TLine) or isinstance(prim, ROOT.TLatex)):
                to_delete.append(prim)
        
        # 在循环外删除
        for prim in to_delete:
            canvas.GetListOfPrimitives().Remove(prim)
        # 或者使用 prim.Delete()
        # 获取y轴范围
        y_min = region['y_min']
        y_max = region['y_max']
        
        # 如果y范围是无穷，使用图形的y轴范围
        if y_min == -np.inf or y_min is None:
            y_min = graph.GetHistogram().GetMinimum()
        if y_max == np.inf or y_max is None:
            y_max = graph.GetHistogram().GetMaximum()
        

        # 设置x轴和y轴范围
        x_min_zoom = region['x_min'] - 0.005
        x_max_zoom = region['x_max'] + 0.005
        
        y_min_zoom = region['y_min'] - 0.01
        y_max_zoom = region['y_max'] + 0.01
        
        # 确保y_min_zoom不为负数
        if y_min_zoom < 0:
            y_min_zoom = 0

        # 应用范围设置
        graph.GetHistogram().GetXaxis().SetRangeUser(x_min_zoom, x_max_zoom)
        graph.GetHistogram().GetYaxis().SetRangeUser(y_min_zoom, y_max_zoom)       
        # 修改simulation_lines中位于当前x范围内的线的y2和label的y位置
        for sim_line in simulation_lines:
            freq = sim_line['frequency']
            if x_min_zoom <= freq <= x_max_zoom:
                # 创建新的线，而不是修改原有的
                new_line = ROOT.TLine(freq, y_min_zoom, freq, y_max_zoom)
                new_line.SetLineColor(sim_line['color'])
                new_line.SetLineWidth(2)
                new_line.DrawClone()                
                # 重新绘制标签（需要先删除旧的？或者直接创建新的）
                new_label = ROOT.TLatex()
                new_label.SetTextSize(0.018)
                new_label.SetTextColor(sim_line['color'])
                new_label.SetTextAngle(90)
                new_label.SetTextFont(42)
                label_text = f"{sim_line['ion_name']} (n={sim_line['harmonic']}, y={sim_line['yield_value']:.2e} pps)"
                new_label.DrawLatex(freq, y_max_zoom , label_text)
                
                # 更新sim_line中的label引用
                sim_line['line'] = new_line
                sim_line['label'] = new_label
                
        # 创建矩形框
        box = ROOT.TBox(region['x_min'], y_min, region['x_max'], y_max)
        color = colors[i % len(colors)]
        box.SetFillStyle(0)  # 设置为空心（不填充）
        box.SetLineColor(color)
        box.SetLineWidth(2)
        box.SetLineStyle(2)  # 虚线
        box.DrawClone()
        boxes.append(box)
        
        # 添加区域标签
        label = ROOT.TLatex()
        label.SetTextSize(0.025)
        label.SetTextColor(color)
        label.SetTextFont(42)
        
        # 标签位置：在矩形框的左上角
        label_x = region['x_min'] + (region['x_max'] - region['x_min']) * 0.02
        label_y = y_max * 0.95
        
        # 使用区域名称（如果提供了名称）
        label_text = region.get('name', f"Region {i+1}")
        label.DrawLatex(label_x, label_y, label_text)
        boxe_labels.append(label)
        
        print(f"绘制区域 {i+1}: {label_text}")
        print(f"  X范围: [{region['x_min']:.6f}, {region['x_max']:.6f}] MHz")
        print(f"  Y范围: [{y_min:.6e}, {y_max:.6e}]")
    
        # 根据save_images参数决定是否保存PNG图片
        if save_images:
            # 更新画布
            canvas.Update()
            # 保存为PNG图片
            # 生成文件名（去除可能的不合法文件名字符）
            safe_name = label_text.replace(' ', '_').replace('/', '_')
            filename = f"analysis_results/{safe_name}.png"
            canvas.SaveAs(filename)
            filename = f"analysis_results/{safe_name}.root"
            canvas.SaveAs(filename)
            print(f"  已保存图片: {filename}")
        
    # 输出详细范围信息
    print(f"  图片X范围: [{x_min_zoom:.6f}, {x_max_zoom:.6f}] MHz")
        
    canvas.Update()
    return boxes,boxe_labels


def analyze_multiple_regions(frequencies, areas_per_frame, full_lines, region_strings, output_dir):
    """
    分析多个区域并保存结果
    
    Parameters:
    -----------
    frequencies : np.ndarray
        频率数组
    areas_per_frame : np.ndarray
        每frame面积数组
    full_lines : list
        完整的原始数据行列表
    region_strings : list
        区域字符串列表，支持格式: 'x_min,x_max', 'x_min,x_max,y_min,y_max', 或 'x_min,x_max,y_min,y_max,region_name'
    output_dir : str
        输出目录
    
    Returns:
    --------
    list : 所有区域的分析结果列表
    """
    results = []
    
    # 创建输出目录
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    for i, region_str in enumerate(region_strings):
        try:
            # 解析区域字符串
            region_info = parse_region_string(region_str)
            
            print(f"\n分析区域 {i+1}: {region_info['name']}")
            print(f"  X范围: [{region_info['x_min']}, {region_info['x_max']}]")
            if region_info['y_min'] is not None and region_info['y_max'] is not None:
                print(f"  Y范围: [{region_info['y_min']}, {region_info['y_max']}]")
            else:
                print(f"  Y范围: 无限制")
            
            result = analyze_region(frequencies, areas_per_frame, full_lines,
                                   region_info['x_min'], region_info['x_max'],
                                   region_info['y_min'], region_info['y_max'],
                                   region_info['name'])
            results.append(result)
            
            # 打印结果
            print(f"  找到 {result['n_points']} 个数据点")
            if result['n_points'] > 0:
                print(f"  频率平均值: {result['freq_mean']:.6f} ± {result['freq_std']:.6f} MHz")
                print(f"  每frame面积平均值: {result['area_mean']:.6e} ± {result['area_std']:.6e}")
                print(f"  每frame面积总和: {result['area_sum']:.6e}")
            else:
                print(f"  警告: 未找到数据点")
                
        except ValueError as e:
            print(f"警告: {e}")
            continue
    
    # 保存结果到文件
    if output_dir:
        save_analysis_results(results, output_dir)
    
    return results


def save_analysis_results(results, output_dir):
    """
    保存分析结果到文件
    
    Parameters:
    -----------
    results : list
        分析结果列表
    output_dir : str
        输出目录
    """
    # 保存为JSON格式（便于程序读取）
    json_file = os.path.join(output_dir, "region_analysis.json")
    json_results = []
    for i, result in enumerate(results):
        # 计算唯一文件名数量
        unique_files = set()
        for line in result['selected_lines']:
            parts = line.split()
            if len(parts) >= 12:
                filename = ' '.join(parts[11:]) if len(parts) > 11 else ""
                if filename:
                    unique_files.add(filename)
        
        json_results.append({
            'region_index': i + 1,
            'name': result['name'],
            'x_min': result['x_min'],
            'x_max': result['x_max'],
            'y_min': result['y_min'] if result['y_min'] != -np.inf else None,
            'y_max': result['y_max'] if result['y_max'] != np.inf else None,
            'n_points': result['n_points'],
            'n_files': len(unique_files),  # 添加文件数量
            'freq_mean': result['freq_mean'],
            'freq_std': result['freq_std'],
            'area_mean': result['area_mean'],
            'area_std': result['area_std'],
            'area_sum': result['area_sum'],
            'selected_lines': result['selected_lines']
        })
    
    with open(json_file, 'w') as f:
        json.dump(json_results, f, indent=2)
    print(f"\nJSON格式的分析结果已保存到: {json_file}")
    
    # 保存为文本格式（便于阅读）
    txt_file = os.path.join(output_dir, "region_analysis.txt")
    with open(txt_file, 'w') as f:
        f.write("=" * 100 + "\n")
        f.write("区域分析结果\n")
        f.write("=" * 100 + "\n\n")
        
        for i, result in enumerate(results):
            # 计算唯一文件名数量
            unique_files = set()
            for line in result['selected_lines']:
                parts = line.split()
                if len(parts) >= 12:
                    filename = ' '.join(parts[11:]) if len(parts) > 11 else ""
                    if filename:
                        unique_files.add(filename)
            
            f.write(f"区域 {i+1}: {result['name']}\n")
            f.write(f"  X范围: [{result['x_min']}, {result['x_max']}] MHz\n")
            y_min_str = f"{result['y_min']:.6e}" if result['y_min'] != -np.inf else "-inf"
            y_max_str = f"{result['y_max']:.6e}" if result['y_max'] != np.inf else "inf"
            f.write(f"  Y范围: [{y_min_str}, {y_max_str}]\n")
            f.write(f"  数据点数: {result['n_points']}\n")
            f.write(f"  文件数目: {len(unique_files)}\n")  # 添加文件数目显示
            
            if result['n_points'] > 0:
                f.write(f"  频率平均值: {result['freq_mean']:.6f} ± {result['freq_std']:.6f} MHz\n")
                f.write(f"  每frame面积平均值: {result['area_mean']:.6e} ± {result['area_std']:.6e}\n")
                f.write(f"  每frame面积总和: {result['area_sum']:.6e}\n")
                f.write(f"\n  详细数据（原始格式）:\n")
                f.write(f"  " + "-" * 98 + "\n")
                # 写入列标题（根据新格式）
                f.write(f"  {'总序号':<8} {'峰序号':<8} {'频率[MHz]':<12} {'峰高':<10} {'FWHM[MHz]':<10} "
                       f"{'start[s]':<10} {'end[s]':<10} {'寿命[s]':<10} {'寿命[frame]':<10} "
                       f"{'面积':<12} {'每frame面积':<12} 文件名\n")
                f.write(f"  " + "-" * 98 + "\n")
                
                for line in result['selected_lines']:
                    # 分割原始行
                    parts = line.split()
                    if len(parts) >= 12:
                        # 文件名可能包含空格，需要特殊处理
                        # 前11列是数据，剩余的是文件名
                        data_parts = parts[:11]
                        filename = ' '.join(parts[11:]) if len(parts) > 11 else ""
                        f.write(f"  {data_parts[0]:<8} {data_parts[1]:<8} {data_parts[2]:<12} {data_parts[3]:<10} "
                               f"{data_parts[4]:<10} {data_parts[5]:<10} {data_parts[6]:<10} {data_parts[7]:<10} "
                               f"{data_parts[8]:<10} {data_parts[9]:<12} {data_parts[10]:<12} {filename}\n")
                    else:
                        f.write(f"  {line}\n")
            else:
                f.write(f"  未找到数据点\n")
            f.write("\n" + "-" * 100 + "\n\n")
    
    print(f"文本格式的分析结果已保存到: {txt_file}")
    
    # 生成汇总报告（CSV格式）
    csv_file = os.path.join(output_dir, "region_summary.csv")
    with open(csv_file, 'w') as f:
        # 写入标题行
        f.write("Region,Name,X_min (MHz),X_max (MHz),Y_min,Y_max,N_points,N_files,Freq_mean (MHz),Freq_std (MHz),Area_mean,Area_std,Area_sum\n")
        
        # 写入数据行
        for i, result in enumerate(results):
            # 计算唯一文件名数量
            unique_files = set()
            for line in result['selected_lines']:
                parts = line.split()
                if len(parts) >= 12:
                    filename = ' '.join(parts[11:]) if len(parts) > 11 else ""
                    if filename:
                        unique_files.add(filename)
            
            y_min_str = f"{result['y_min']:.6e}" if result['y_min'] != -np.inf else "-inf"
            y_max_str = f"{result['y_max']:.6e}" if result['y_max'] != np.inf else "inf"
            f.write(f"{i+1},{result['name']},{result['x_min']},{result['x_max']},{y_min_str},{y_max_str},")
            f.write(f"{result['n_points']},{len(unique_files)},")  # 添加文件数量
            f.write(f"{result['freq_mean']:.6f},{result['freq_std']:.6f},")
            f.write(f"{result['area_mean']:.6e},{result['area_std']:.6e},{result['area_sum']:.6e}\n")
    
    print(f"CSV格式的汇总报告已保存到: {csv_file}")


def save_plot(canvas, output_filename):
    """
    保存图形到文件
    
    Parameters:
    -----------
    canvas : ROOT.TCanvas
        ROOT画布对象
    output_filename : str
        输出文件名
    """
    try:
        canvas.SaveAs(output_filename)
        print(f"图形已保存到: {output_filename}")
    except Exception as e:
        print(f"保存图形时出错: {e}")


def main():
    """主函数"""
    # 设置命令行参数解析
    parser = argparse.ArgumentParser(
        description="读取峰值数据文件并绘制频率 vs 每frame面积的TGraph，同时添加仿真结果的谐波线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法（显示指定范围并分析多个区域）
  python script.py all_peaks_summary.txt -s simulation_result.out -min 0 -max 1000 \\
    --x-min 309.73 --x-max 309.74 --y-min 0 --y-max 0.5 --yield-threshold 1e-15 \\
    -o output.png --analyze-regions "309.5,310.0" "310.5,311.0,0,0.5" "311.2,311.8"
  
  # 带区域名称的用法
  python script.py all_peaks_summary.txt -s simulation_result.out -min 0 -max 1000 \\
    --x-min 310.1 --x-max 310.2 --y-min 0 --y-max 0.5 --yield-threshold 1e-15 \\
    -o analysis_results/ --analyze-regions "310.12703,310.12781,0.00381,0.01207,200Ir77+"
        """
    )
    
    parser.add_argument(
        "filenames",
        type=str,
        nargs='+',  # 接受一个或多个文件名
        help="输入数据文件路径，可以指定多个文件 (如: file1.txt file2.txt file3.txt)"
    )
    
    parser.add_argument(
        "-s", "--simulation",
        type=str,
        default="simulation_result.out",
        help="仿真结果文件路径 (默认: simulation_result.out)"
    )
    
    parser.add_argument(
        "-min", "--harmonic_min",
        type=int,
        required=True,
        help="最小谐波数 (例如: 0)"
    )
    
    parser.add_argument(
        "-max", "--harmonic_max",
        type=int,
        required=True,
        help="最大谐波数 (例如: 1000)"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="输出图像文件名 (如: plot.png, plot.pdf) 或输出目录（当使用--analyze-regions时）"
    )
    
    parser.add_argument(
        "-t", "--title",
        type=str,
        default=None,
        help="图形标题"
    )
    
    parser.add_argument(
        "--x-min",
        type=float,
        default=None,
        help="X轴最小值 (单位: MHz) - 主显示范围"
    )
    
    parser.add_argument(
        "--x-max",
        type=float,
        default=None,
        help="X轴最大值 (单位: MHz) - 主显示范围"
    )
    
    parser.add_argument(
        "--y-min",
        type=float,
        default=None,
        help="Y轴最小值 - 主显示范围"
    )
    
    parser.add_argument(
        "--y-max",
        type=float,
        default=None,
        help="Y轴最大值 - 主显示范围"
    )
    
    parser.add_argument(
        "--yield-threshold",
        type=float,
        default=None,
        help="Yield阈值 (单位: pps)。只绘制yield > 阈值的谐波线。例如: 1e-15"
    )
    
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="不显示图形窗口（仅保存文件）"
    )
    
    parser.add_argument(
        "--no-harmonics",
        action="store_true",
        help="不绘制谐波线"
    )
    
    parser.add_argument(
        "--analyze-regions",
        type=str,
        nargs='+',
        help="分析指定区域并在图上绘制框。支持格式: 'x_min,x_max', 'x_min,x_max,y_min,y_max', 或 'x_min,x_max,y_min,y_max,region_name'"
    )
    parser.add_argument(
        "--save-region-images",
        action="store_true",
        default=True,
        help="保存每个分析区域的单独PNG图片（默认: True）"
    )
    
    parser.add_argument(
        "--no-save-region-images",
        action="store_false",
        dest="save_region_images",
        help="不保存每个分析区域的单独PNG图片"
    )    
    # 解析参数
    args = parser.parse_args()
    
    # 验证谐波数范围
    if args.harmonic_min > args.harmonic_max:
        print(f"错误: 最小谐波数 ({args.harmonic_min}) 不能大于最大谐波数 ({args.harmonic_max})")
        sys.exit(1)
    
    # 验证坐标轴范围
    if args.x_min is not None and args.x_max is not None and args.x_min >= args.x_max:
        print(f"错误: X轴最小值 ({args.x_min}) 必须小于 X轴最大值 ({args.x_max})")
        sys.exit(1)
    
    if args.y_min is not None and args.y_max is not None and args.y_min >= args.y_max:
        print(f"错误: Y轴最小值 ({args.y_min}) 必须小于 Y轴最大值 ({args.y_max})")
        sys.exit(1)
    
    # 验证yield阈值
    if args.yield_threshold is not None and args.yield_threshold < 0:
        print(f"错误: Yield阈值 ({args.yield_threshold}) 必须为非负数")
        sys.exit(1)
    
    # 处理输出文件名和目录
    output_dir = None
    output_image = args.output
    
    if args.analyze_regions:
        # 如果有区域分析，output应该是目录
        if args.output:
            output_dir = args.output
            # 在主目录下保存主图形
            output_image = os.path.join(output_dir, "main_plot.png")
        else:
            print("错误: 使用 --analyze-regions 时必须指定 -o 输出目录")
            sys.exit(1)
    
    try:
        
        # 1. 读取峰值数据（包含完整行）
        print(f"正在读取 {len(args.filenames)} 个峰值文件:")
        frequencies, areas_per_frame, full_lines = merge_multiple_peaks_files(args.filenames)
        
        print(f"成功读取 {len(frequencies)} 个数据点")
        print(f"原始频率范围: {frequencies.min():.6f} - {frequencies.max():.6f} MHz")
        print(f"原始每frame面积范围: {areas_per_frame.min():.6e} - {areas_per_frame.max():.6e}")
        
        # 2. 创建并绘制主图形（使用--x-min, --x-max, --y-min, --y-max指定的范围）
        print("\n" + "="*60)
        print("绘制主显示区域:")
        print("="*60)
        canvas, graph = create_and_plot_graph(frequencies, areas_per_frame, args.title,
                                             args.x_min, args.x_max, 
                                             args.y_min, args.y_max)
        
        # 3. 添加谐波线（如果不跳过）
        if not args.no_harmonics:
            print(f"\n正在读取仿真文件: {args.simulation}")
            sim_frequencies, sim_yields, ion_names = read_simulation_results(args.simulation)
            
            if len(sim_frequencies) > 0:
                print(f"谐波数范围: {args.harmonic_min} 到 {args.harmonic_max}")
                print(f"仿真频率数量: {len(sim_frequencies)}")
                print(f"仿真yield范围: {sim_yields.min():.2e} - {sim_yields.max():.2e} pps")
                if args.yield_threshold is not None:
                    print(f"使用yield阈值: {args.yield_threshold:.2e} pps")
                
                # 获取实际的x轴范围（用于过滤）
                x_min_display = args.x_min if args.x_min is not None else graph.GetXaxis().GetXmin()
                x_max_display = args.x_max if args.x_max is not None else graph.GetXaxis().GetXmax()
                print(f"绘制谐波线时使用的x轴范围: [{x_min_display}, {x_max_display}] MHz")
                
                # 添加谐波线
                simulation_lines = add_harmonic_lines_simple(canvas, graph, sim_frequencies, sim_yields,
                                 args.harmonic_min, args.harmonic_max, ion_names,
                                 x_min_display, x_max_display, args.yield_threshold)
            else:
                print("警告: 未能读取仿真数据，跳过谐波线绘制")
        
        # 4. 分析并绘制区域（如果指定）
        if args.analyze_regions:
            print("\n" + "="*60)
            print("分析指定区域:")
            print("="*60)
            
            # 分析区域（传入完整行）
            results = analyze_multiple_regions(frequencies, areas_per_frame, full_lines,
                                               args.analyze_regions, output_dir)
            
            # 准备用于绘制的区域数据
            regions_for_drawing = []
            for region_str in args.analyze_regions:
                try:
                    region_info = parse_region_string(region_str)
                    regions_for_drawing.append(region_info)
                except ValueError as e:
                    print(f"警告: {e}")
                    continue
            
            # 在图形上绘制区域框
            if regions_for_drawing:
                print("\n在图形上绘制区域框...")
                draw_region_boxes(canvas, graph, regions_for_drawing, simulation_lines, save_images=args.save_region_images)
                
        
        # 5. 保存主图形
        if output_image:
            save_plot(canvas, output_image)
        
        # 6. 显示图形
        if not args.no_show:
            print("\n图形已显示。按回车键退出...")
            input()
        
    except FileNotFoundError as e:
        print(f"\n错误: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\n错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
