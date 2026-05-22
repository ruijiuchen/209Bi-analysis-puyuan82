#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import argparse
from pathlib import Path
import ROOT

# ====================== 全局设置 ======================
ROOT.gROOT.SetBatch(True)
ROOT.gErrorIgnoreLevel = ROOT.kError
gStyle = ROOT.gStyle

gStyle.SetPalette(51)
gStyle.SetNumberContours(255)
gStyle.SetOptStat(0)


def set_axis_style(h, title_size=0.055, label_size=0.05, title_offset=1.1):
    """统一坐标轴样式"""
    font = 42
    for axis in [h.GetXaxis(), h.GetYaxis()]:
        axis.SetTitleSize(title_size)
        axis.SetLabelSize(label_size)
        axis.SetTitleOffset(title_offset)
        axis.SetTitleFont(font)
        axis.SetLabelFont(font)
        axis.CenterTitle(True)
    if hasattr(h, 'GetZaxis') and h.GetZaxis():
        h.GetZaxis().SetTitleSize(title_size * 0.9)
        h.GetZaxis().SetLabelSize(label_size * 0.9)
        h.GetZaxis().SetTitleOffset(0.05)
        h.GetZaxis().SetTitleFont(font)
        h.GetZaxis().SetLabelFont(font)
        h.GetZaxis().CenterTitle(True)

def estimate_fwhm(h1, peak_center, peak_height):
    """在峰附近估算 FWHM（Full Width at Half Maximum）"""
    if peak_height <= 0:
        return 0.0
    
    half_height = peak_height * 0.5
    x_axis = h1.GetXaxis()
    bin_center = x_axis.FindBin(peak_center)
    n_bins = h1.GetNbinsX()
    
    # 向左找半高点
    left_bin = bin_center
    for b in range(bin_center, 0, -1):
        if h1.GetBinContent(b) < half_height:
            left_bin = b
            break
    
    # 向右找半高点
    right_bin = bin_center
    for b in range(bin_center, n_bins + 1):
        if h1.GetBinContent(b) < half_height:
            right_bin = b
            break
    
    left_x = x_axis.GetBinCenter(left_bin)
    right_x = x_axis.GetBinCenter(right_bin)
    
    fwhm = abs(right_x - left_x)
    return fwhm
    
def find_peak_near_center(h1, center_guess, width_guess):
    """
    在指定中心附近使用 TSpectrum 搜索真实峰位
    
    返回: (peak_center, peak_height, peak_fwhm)
    """
    if h1 is None:
        return center_guess, 0.0, width_guess

    # 创建 TSpectrum 对象
    spectrum = ROOT.TSpectrum()
    
    # 设置搜索范围（建议在 guess 附近 ± 一定范围，避免找错峰）
    search_range = max(3.0 * width_guess, 10.0)   # 可根据需要调整
    
    # 使用 Search 函数在直方图上找峰
    # 参数说明:
    #   - npeaks: 最多找几个峰（我们只关心一个）
    #   - threshold: 峰的显著性阈值（相对高度），通常 0.01~0.1
    #   - option: "goff" 表示不画图，只找峰；"nodraw" 也常用
    npeaks = spectrum.Search(h1, search_range, "goff nodraw", 0.05)
    
    if npeaks == 0:
        # 没找到峰，回退到原始简单方法
        return find_peak_near_center_simple(h1, center_guess, width_guess)
    
    # 获取 TSpectrum 找到的所有峰的位置和高度
    peak_positions = spectrum.GetPositionX()   # 数组指针
    peak_heights   = spectrum.GetPositionY()
    
    # 在找到的峰中，挑选最接近 center_guess 的那个
    best_idx = 0
    min_distance = float('inf')
    
    for i in range(npeaks):
        pos = peak_positions[i]
        distance = abs(pos - center_guess)
        if distance < min_distance:
            min_distance = distance
            best_idx = i
    
    peak_center = peak_positions[best_idx]
    peak_height = peak_heights[best_idx]
    
    # ====================== 估算宽度 (FWHM) ======================
    # 方法1：使用 TSpectrum 的 GetResolution()（如果可用）
    # 方法2：更稳健的做法是在峰附近找半高宽
    fwhm = estimate_fwhm(h1, peak_center, peak_height)
    
    # 如果估算失败，回退到 width_guess
    if fwhm <= 0:
        fwhm = width_guess
    
    return peak_center, peak_height, fwhm


def perform_gaussian_fit_and_plot(h1, h2, hist_name="h1", processing_log=None,
                                  original_filename="", plot_dir=None,
                                  freq_tgt=None, freq_width_tgt=None,
                                  t_min=None, t_max=None, freq_low=None, freq_high=None,
                                  amp_threshold=0.005, z_min=None, z_max=None,
                                  correct_frequency=False, lifetime=None,
                                  logz=True, skip_low_peak_check=False):  # 新增参数
    """
    执行高斯拟合并可选进行频率修正。
    画布改为 2x2 布局：
        左上: h2 (原始)          右上: h2_corrected (修正后)
        左下: h1 (原始)          右下: h1_corrected + Gaussian Fit
    
    返回: (fit_func, h1_corrected, h2_corrected)
    """

    # ==================== 初始峰搜索 ====================
    if freq_tgt is not None and freq_width_tgt is not None:
        x_guess, y_peak, fwhm_peak = find_peak_near_center(h1, freq_tgt / 1e6, 2 * freq_width_tgt / 1e6)
        sigma_guess = fwhm_peak / 2.35
        amp_guess = y_peak
        source = "固定+搜峰"
    else:
        max_bin = h1.GetMaximumBin()
        x_guess = h1.GetXaxis().GetBinCenter(max_bin)
        y_peak = h1.GetMaximum()
        sigma_guess = h1.GetRMS() * 0.35
        amp_guess = y_peak
        source = "自动"

    # 修改：只有当 skip_low_peak_check 为 False 时才检查峰高
    if not skip_low_peak_check and y_peak < amp_threshold:
        if processing_log is not None:
            processing_log.append(f"SKIP\t{original_filename}\t峰高太低\t{y_peak:.5f}")
        return None, None, None
    
    # ==================== 第一次拟合 ====================
    fit_xmin = max(h1.GetXaxis().GetXmin(), x_guess - 4.0 * sigma_guess)
    fit_xmax = min(h1.GetXaxis().GetXmax(), x_guess + 4.0 * sigma_guess)

    fit_func = ROOT.TF1(f"gaus_fit_{hist_name}", "gaus(0)", fit_xmin, fit_xmax)
    fit_func.SetParameter(0, amp_guess)
    fit_func.SetParameter(1, x_guess)
    fit_func.SetParameter(2, sigma_guess)
    
    h1.Fit(fit_func, "R S M E")   # 加上 E (使用 Minos 改善误差)
    fit_func.SetNpx(1000)           # 画图更平滑
    
    mu = fit_func.GetParameter(1)
    mu_err = fit_func.GetParError(1)
    amp = fit_func.GetParameter(0)
    amp_err = fit_func.GetParError(0)
    sigma = fit_func.GetParameter(2)
    sigma_err = fit_func.GetParError(2)
    chi2 = fit_func.GetChisquare()
    ndf = fit_func.GetNDF()
    chi2_ndf = f"{chi2/ndf:.4f}" if ndf > 0 else "inf"

    # ==================== 频率修正 ====================
    h1_corrected = h1
    h2_corrected = h2
    delta_freq = 0.0


    if correct_frequency and freq_tgt is not None:
        freq_tgt_mhz = freq_tgt / 1e6
        delta_freq = freq_tgt_mhz - mu

        if abs(delta_freq) > 1e-6:
            print(f" → 频率修正: mu = {mu:.5f} MHz → 目标 {freq_tgt_mhz:.5f} MHz, 偏移 = {delta_freq:.5f} MHz")
            
            # ====================== 创建修正后对象（轴范围完全不变） ======================
            h1_corrected = h1.Clone(f"{h1.GetName()}_corr")
            # 轴范围保持原始不变
            # h1_corrected.GetXaxis().Set(...)   # 这一步不再执行
            
            # 把内容向右平移 delta_freq（如果 delta_freq > 0，则峰向右移动）
            n_bins = h1_corrected.GetNbinsX()
            bin_width = h1_corrected.GetXaxis().GetBinWidth(1)
            
            # 使用临时数组保存新内容（推荐方式，避免覆盖时出错）
            new_contents = [0.0] * (n_bins + 2)   # 包含 underflow 和 overflow
            
            for b in range(1, n_bins + 1):
                old_x = h1.GetXaxis().GetBinCenter(b)
                new_x = old_x + delta_freq
                # 找到新 x 对应的 bin
                new_bin = h1_corrected.GetXaxis().FindBin(new_x)
                
                if 1 <= new_bin <= n_bins:
                    content = h1.GetBinContent(b)
                    error = h1.GetBinError(b)
                    new_contents[new_bin] += content
                    # 如果需要保留误差，可简单相加或使用更精确方式
                    # new_errors[new_bin] = ... 
            
            # 把新内容写回 histogram
            for b in range(1, n_bins + 1):
                h1_corrected.SetBinContent(b, new_contents[b])
                # h1_corrected.SetBinError(b, new_errors[b])   # 如有需要
            
            # ====================== 对 h2_corrected 做同样处理 ======================
            if h2 and isinstance(h2, ROOT.TH2F):
                h2_corrected = h2.Clone(f"{h2.GetName()}_corr")
                # Y 轴和 X 轴范围保持不变
                
                ny = h2_corrected.GetNbinsY()
                nx = h2_corrected.GetNbinsX()
                
                # 为简单起见，这里采用逐 bin 平移 X（Y 不变）
                for by in range(1, ny + 1):
                    for bx in range(1, nx + 1):
                        old_x = h2.GetXaxis().GetBinCenter(bx)
                        new_x = old_x + delta_freq
                        new_bx = h2_corrected.GetXaxis().FindBin(new_x)
                        
                        if 1 <= new_bx <= nx:
                            content = h2.GetBinContent(bx, by)
                            h2_corrected.SetBinContent(new_bx, by, content)
                            # 可选：处理误差 h2_corrected.SetBinError(...)
                
                # 清空原始位置的内容（防止重叠残留）
                # （上面已经用新位置覆盖，这里可选择性清空旧 bin，但通常不必要）
            
        else:
            # 不需要修正时，直接使用原始对象
            h1_corrected = h1
            h2_corrected = h2

            # 使用修正后的 h1 重新拟合
            x_guess = freq_tgt_mhz
            fit_xmin = max(h1_corrected.GetXaxis().GetXmin(), x_guess - 8.0 * sigma)
            fit_xmax = min(h1_corrected.GetXaxis().GetXmax(), x_guess + 8.0 * sigma)

            fit_func = ROOT.TF1(f"gaus_fit_{hist_name}_corr", "gaus(0) + pol1(3)", fit_xmin, fit_xmax)
            fit_func.SetParameter(0, amp)
            fit_func.SetParameter(1, x_guess)
            fit_func.SetParameter(2, sigma)
            fit_func.SetParameter(3, 0.0)
            fit_func.SetParameter(4, 0.0)

            h1_corrected.Fit(fit_func, "R Q S M")

            # 更新拟合参数
            mu = fit_func.GetParameter(1)
            mu_err = fit_func.GetParError(1)
            amp = fit_func.GetParameter(0)
            amp_err = fit_func.GetParError(0)
            sigma = fit_func.GetParameter(2)
            sigma_err = fit_func.GetParError(2)
            chi2 = fit_func.GetChisquare()
            ndf = fit_func.GetNDF()
            chi2_ndf = f"{chi2/ndf:.4f}" if ndf > 0 else "inf"

            source += " + 频率修正"

    # ==================== 保存处理日志 ====================
    if processing_log is not None:
        row = (f"{original_filename}\t"
               f"{x_guess:.5f}\t{sigma_guess:.5f}\t{y_peak:.5f}\t"
               f"{mu:.5f}\t{mu_err:.5f}\t"
               f"{amp:.5f}\t{amp_err:.5f}\t"
               f"{sigma:.5f}\t{sigma_err:.5f}\t"
               f"{chi2:.3f}\t{ndf}\t{chi2_ndf}\t{source}")
        if correct_frequency and abs(delta_freq) > 1e-6:
            row += f"\t{lifetime:.5f}"
        processing_log.append(row)

    # ==================== 2x2 画布绘图 ====================
    try:
        c = ROOT.TCanvas(f"c_{hist_name}", f"{original_filename} - 2x2 Comparison", 1800, 1400)
        
        # 定义四个 Pad 的位置 (left, bottom, right, top)
        pad_left_top   = ROOT.TPad("pad_lt", "h2 original",    0.00, 0.50, 0.50, 1.00)
        pad_left_bot   = ROOT.TPad("pad_lb", "h1 original",    0.00, 0.00, 0.50, 0.50)
        pad_right_top  = ROOT.TPad("pad_rt", "h2 corrected",   0.50, 0.50, 1.00, 1.00)
        pad_right_bot  = ROOT.TPad("pad_rb", "h1 corrected",   0.50, 0.00, 1.00, 0.50)

        for pad in [pad_left_top, pad_left_bot, pad_right_top, pad_right_bot]:
            pad.SetLeftMargin(0.12)
            pad.SetRightMargin(0.15)
            pad.SetBottomMargin(0.2 if pad in [pad_left_bot, pad_right_bot] else 0.2)
            pad.SetTopMargin(0.10)
            pad.Draw()

        # ====================== 左上：原始 h2 ======================
        pad_left_top.cd()
        if h2 and isinstance(h2, ROOT.TH2F):
            h2.SetTitle(f"{original_filename} - TH2F Original")
            h2.SetStats(0)
            h2.GetXaxis().SetNdivisions(505)
            if freq_low and freq_high:
                h2.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
            h2.Draw("COLZ")
            if logz:  # 使用 logz 参数控制
                pad_left_top.SetLogz(True)
            set_axis_style(h2)

            if z_min is not None: h2.SetMinimum(z_min)
            if z_max is not None: h2.SetMaximum(z_max)

            # 绿色辅助线
            if freq_low and freq_high:
                line_lifetime = ROOT.TLine(freq_low/1e6, lifetime, freq_high/1e6, lifetime)
                line_lifetime.SetLineColor(ROOT.kGreen); line_lifetime.SetLineStyle(2); line_lifetime.SetLineWidth(2); line_lifetime.Draw()
            # 绿色辅助线
            print("chenrj ... t_min = ",t_min)
            if t_min:
                line_t_min = ROOT.TLine(freq_low/1e6, t_min, freq_high/1e6, t_min)
                line_t_min.SetLineColor(ROOT.kPink); line_t_min.SetLineStyle(2); line_t_min.SetLineWidth(2); line_t_min.Draw()
            # 绿色辅助线
            if t_max:
                line_t_max = ROOT.TLine(freq_low/1e6, t_max, freq_high/1e6, t_max)
                line_t_max.SetLineColor(ROOT.kPink); line_t_max.SetLineStyle(2); line_t_max.SetLineWidth(2); line_t_max.Draw()

        # ====================== 左下：原始 h1 ======================
        pad_left_bot.cd()
        h1.SetLineColor(ROOT.kBlue)
        h1.SetLineWidth(2)
        h1.SetTitle(f"{original_filename} - TH1F Original;Frequency [MHz];Counts")
        h1.GetXaxis().SetNdivisions(505)
        if freq_low and freq_high:
            h1.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
        h1.Draw("HIST")

        fit_func.SetLineColor(ROOT.kRed)
        fit_func.SetLineWidth(2)
        fit_func.Draw("SAME")
        # 幅度阈值线和频率区间线
        if amp_threshold is not None and freq_tgt and freq_width_tgt:
            f_low = (freq_tgt - freq_width_tgt/2)/1e6
            f_high = (freq_tgt + freq_width_tgt/2)/1e6
            line_amp = ROOT.TLine(f_low, amp_threshold, f_high, amp_threshold)
            line_amp.SetLineColor(ROOT.kRed); line_amp.SetLineStyle(2); line_amp.SetLineWidth(2); line_amp.Draw()

            line_f1 = ROOT.TLine(f_low, 0, f_low, amp_threshold)
            line_f2 = ROOT.TLine(f_high, 0, f_high, amp_threshold)
            line_f1.SetLineColor(ROOT.kRed); line_f1.SetLineStyle(2); line_f1.SetLineWidth(2); line_f1.Draw()
            line_f2.SetLineColor(ROOT.kRed); line_f2.SetLineStyle(2); line_f2.SetLineWidth(2); line_f2.Draw()

        # 图例和拟合信息（放在右下）
        legend = ROOT.TLegend(0.60, 0.72, 0.88, 0.88)
        legend.AddEntry(h1_corrected, "Data", "l")
        legend.AddEntry(fit_func, "Gaussian + pol1 BG", "l")
        legend.Draw()

        text = ROOT.TPaveText(0.15, 0.55, 0.55, 0.82, "NDC")
        text.SetFillColor(0)
        text.AddText(f"#mu = {mu:.5f} #pm {mu_err:.5f} MHz")
        text.AddText(f"#sigma = {sigma:.5f} #pm {sigma_err:.5f} MHz")
        text.AddText(f"Amplitude = {amp:.5f} #pm {amp_err:.5f}")
        if correct_frequency and abs(delta_freq) > 1e-6:
            text.AddText(f"Corrected by {delta_freq:.5f} MHz")
        text.Draw()
        # ====================== 右上：修正后 h2 ======================
        pad_right_top.cd()
        if h2_corrected and isinstance(h2_corrected, ROOT.TH2F):
            suffix = " (Frequency Corrected)" if correct_frequency and abs(delta_freq) > 1e-6 else ""
            h2_corrected.SetTitle(f"{original_filename} - TH2F{suffix}")
            h2_corrected.SetStats(0)
            h2_corrected.GetXaxis().SetNdivisions(505)
            if freq_low and freq_high:
                h2_corrected.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
            h2_corrected.Draw("COLZ")
            if logz:  # 使用 logz 参数控制
                pad_right_top.SetLogz(True)
            set_axis_style(h2_corrected)

            if z_min is not None: h2_corrected.SetMinimum(z_min)
            if z_max is not None: h2_corrected.SetMaximum(z_max)

        # ====================== 右下：修正后 h1 + 拟合 ======================
        pad_right_bot.cd()
        h1_corrected.SetLineColor(ROOT.kBlue)
        h1_corrected.SetLineWidth(2)
        h1_corrected.GetXaxis().SetNdivisions(505)
        suffix = " (Frequency Corrected)" if correct_frequency and abs(delta_freq) > 1e-6 else ""
        h1_corrected.SetTitle(f"{original_filename} - TH1F{suffix} with Gaussian Fit;Frequency [MHz];Counts")
        if freq_low and freq_high:
            h1_corrected.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
        h1_corrected.Draw("HIST")

        # 更新并保存
        c.cd()
        c.Modified()
        c.Update()

        suffix = "_2x2_corr" if correct_frequency and abs(delta_freq) > 1e-6 else "_2x2"
        png_path = plot_dir / f"fit_{original_filename}{suffix}.png"
        c.SaveAs(str(png_path))
        print(f" → 2x2 PNG 已保存: {png_path.name}")

        c.Close()

    except Exception as e:
        print(f" 警告：绘图失败: {e}")

    return fit_func, h1_corrected, h2_corrected
    
def fit_single_histogram(h, hist_name="hist", 
                         freq_tgt=None, freq_width_tgt=None,
                         color=ROOT.kRed):
    """
    对单个 TH1 直方图进行 Gaussian + Linear Background 拟合
    
    参数:
        h:                要拟合的直方图 (TH1F)
        hist_name:        用于命名和打印的名称（如 "sum_h1_corrected"）
        freq_tgt:         目标中心频率 (Hz)，用于设置拟合初始值
        freq_width_tgt:   目标频率宽度 (Hz)
        color:            拟合曲线的颜色
    
    返回:
        fit_func:         拟合函数 TF1
        result:           包含关键拟合参数的字典
    """
    if h is None or not isinstance(h, ROOT.TH1):
        print(f"Warning: {hist_name} is None or not a TH1")
        return None, None


    # 初始猜测值
    max_bin = h.GetMaximumBin()
    x_guess = h.GetXaxis().GetBinCenter(max_bin)
    amp_guess = h.GetMaximum()
    sigma_guess = max(h.GetRMS() * 0.05, 0.00005)
    
    # ====================== 设置拟合范围和初始参数 ======================
    if freq_tgt is not None and freq_width_tgt is not None:
        width = freq_width_tgt / 1e6
        fit_xmin = x_guess - 0.8*width
        fit_xmax = x_guess + 0.8*width
    else:
        fit_xmin = h.GetXaxis().GetXmin()
        fit_xmax = h.GetXaxis().GetXmax()

    # 创建拟合函数
    fit_name = f"gaus_fit_{hist_name}"
    fit_func = ROOT.TF1(fit_name, "gaus(0) + pol1(3)", fit_xmin, fit_xmax)
    fit_func.SetParameter(0, amp_guess)
    fit_func.SetParameter(1, x_guess)
    fit_func.SetParameter(2, sigma_guess)
    fit_func.SetParameter(3, 0.0)
    fit_func.SetParameter(4, 0.0)
    fit_func.SetNpx(1000)   # 更高精度，更平滑
    fit_func.SetParNames("Amplitude", "Mean", "Sigma", "p0", "p1")
    fit_func.SetLineColor(color)
    fit_func.SetLineWidth(2)

    # 执行拟合
    h.Fit(fit_func, "R Q S M")

    # ====================== 提取拟合结果 ======================
    result = {
        'name': hist_name,
        'mu': fit_func.GetParameter(1),
        'mu_err': fit_func.GetParError(1),
        'amp': fit_func.GetParameter(0),
        'amp_err': fit_func.GetParError(0),
        'sigma': fit_func.GetParameter(2),
        'sigma_err': fit_func.GetParError(2),
        'chi2': fit_func.GetChisquare(),
        'ndf': fit_func.GetNDF(),
        'chi2_ndf': fit_func.GetChisquare() / fit_func.GetNDF() if fit_func.GetNDF() > 0 else float('inf')
    }

    print(f"[{hist_name}] 拟合完成 → "
          f"μ = {result['mu']:.5f} ± {result['mu_err']:.5f} MHz | "
          f"σ = {result['sigma']:.5f} MHz | "
          f"χ²/NDF = {result['chi2_ndf']:.3f}")

    return fit_func, result

def calculate_lifetime_from_h2(h2, freq_tgt, freq_width_tgt, amp_threshold=0.005):
    """
    1. 对 h2 在 freq_tgt ± freq_width_tgt 频率区间做 X 轴投影
    2. 将投影内容除以 (bin_high - bin_low) 进行归一化
    3. 从左到右找到第一个 bin 内容 < amp_threshold 的 bin
    4. 返回该 bin 的中心值作为寿命
    
    返回:
        lifetime (float):  计算得到的寿命（秒）
        proj_h1 (TH1D):   处理后的投影直方图（已除以 bin 数）
        status (str):     状态信息
    """
    if h2 is None or not isinstance(h2, ROOT.TH2F):
        return None, None, "Error: h2 is not a valid TH2F"

    # 1. 计算频率区间的 bin 范围
    x_axis = h2.GetXaxis()
    bin_low = x_axis.FindBin(freq_tgt / 1e6 - freq_width_tgt / 1e6)
    bin_high = x_axis.FindBin(freq_tgt / 1e6 + freq_width_tgt / 1e6)

    bin_low = max(1, bin_low)
    bin_high = min(h2.GetNbinsX(), bin_high)

    if bin_low >= bin_high:
        return None, None, "Error: 频率区间 bin 范围无效"

    n_bins_x = bin_high - bin_low + 1   # 参与投影的 X bin 数量
    print(f"投影使用 X bins: {bin_low} ~ {bin_high}  (共 {n_bins_x} 个 bin)")

    # 2. 做 X 轴投影（得到时间方向的直方图）
    proj_name = f"proj_time_{h2.GetName()}"
    proj_h1 = h2.ProjectionY(proj_name, bin_low, bin_high)
    
    proj_h1.SetTitle(f"ProjectionY of {h2.GetName()} (freq_tgt ± freq_width_tgt, normalized);Time [s];Counts per bin")
    proj_h1.SetLineColor(ROOT.kBlue)
    proj_h1.SetLineWidth(2)

    # 4. 从左到右扫描，找到第一个 bin 内容 < amp_threshold 的位置
    n_bins_y = proj_h1.GetNbinsX()
    lifetime = None

    for b in range(1, n_bins_y + 1):
        content = proj_h1.GetBinContent(b)
        if content < amp_threshold:
            lifetime = proj_h1.GetXaxis().GetBinCenter(b)
            break

    # 如果全程都没有低于阈值，则取最后一个 bin
    if lifetime is None:
        lifetime = proj_h1.GetXaxis().GetBinCenter(n_bins_y)
        status = f"Warning: 未找到低于 {amp_threshold} 的 bin，使用最后一个 bin"
    else:
        status = f"Success: 第一个低于 {amp_threshold} 的 bin"

    print(f"[{h2.GetName()}] 寿命计算完成: {lifetime:.6f} s   (status: {status})")

    return lifetime, proj_h1, status

def create_h1_from_lifetime_window(h2, lifetime, freq_tgt=None, freq_width_tgt=None, 
                                   window_width=0.1, window_offset=0.1):
    """
    从 h2 中沿着 Y 轴（时间轴）截取 [lifetime + window_offset, lifetime + window_offset + window_width] 
    区间的内容，然后向 X 轴（频率轴）做投影，生成一个新的 h1。
    
    参数:
        h2:                输入 TH2F
        lifetime:          已计算出的寿命（秒）
        window_offset:     从 lifetime 开始向后偏移多少秒（默认 0.1s）
        window_width:      截取窗口的宽度（默认 0.1s）
        freq_tgt, freq_width_tgt:  可选，用于设置投影标题
    
    返回:
        h1_proj:   投影得到的 TH1F（频率方向）
        y_low:     实际使用的 Y 轴下限
        y_high:    实际使用的 Y 轴上限
    """
    if h2 is None or not isinstance(h2, ROOT.TH2F):
        print("Error: h2 不是有效的 TH2F")
        return None, None, None

    if lifetime is None:
        print("Error: lifetime 为 None，无法截取窗口")
        return None, None, None

    y_axis = h2.GetYaxis()
    
    y_low = window_offset
    y_high = y_low + window_width

    # 找到对应的 bin 范围
    bin_low = y_axis.FindBin(y_low)
    bin_high = y_axis.FindBin(y_high)

    bin_low = max(1, bin_low)
    bin_high = min(h2.GetNbinsY(), bin_high)

    if bin_low >= bin_high:
        print(f"Warning: Y 轴窗口无效 (y_low={y_low:.4f}, y_high={y_high:.4f})")
        return None, y_low, y_high

    # 向 X 轴投影（频率方向）
    proj_name = f"h1_from_lifetime_{h2.GetName()}"
    h1_proj = h2.ProjectionX(proj_name, bin_low, bin_high)
    
    h1_proj.SetName("h1_lifetime_window")
    h1_proj.SetTitle(f"ProjectionX from lifetime window [{y_low:.3f} ~ {y_high:.3f}] s;Frequency [MHz];Counts")
    h1_proj.SetLineColor(ROOT.kRed)
    h1_proj.SetLineWidth(2)

    print(f"已生成 lifetime 窗口投影: Y = [{y_low:.4f} ~ {y_high:.4f}] s "
          f"(bins {bin_low} ~ {bin_high})")

    return h1_proj, y_low, y_high
    
def main():
    parser = argparse.ArgumentParser(description="ROOT 直方图叠加 + 高斯拟合（带辅助线）")

    parser.add_argument("-d", "--dir", action="append", type=str, required=True, help="输入目录路径")
    parser.add_argument("-o", "--output", type=str, default="summed_histograms.root", help="输出 ROOT 文件名")
    
    # 新增：图片输出目录参数
    parser.add_argument("--plot_dir", type=str, default="fit_plots", 
                        help="图片输出目录路径（默认: fit_plots）")
    
    # 新增：控制对数 Z 轴的参数
    parser.add_argument("--logz", action="store_true", default=False,
                        help="启用 Z 轴对数显示（默认: False，使用线性 Z 轴）")
    parser.add_argument("--no-logz", action="store_true", default=False,
                        help="禁用 Z 轴对数显示（覆盖 --logz）")
    
    # 其他参数
    parser.add_argument("--t_min", type=float, default=None, help="投影时间下限 (s)")
    parser.add_argument("--t_max", type=float, default=None, help="投影时间上限 (s)")
    parser.add_argument("--freq_low", type=float, required=True, help="感兴趣频率下限 (Hz)")
    parser.add_argument("--freq_high", type=float, required=True, help="感兴趣频率上限 (Hz)")
    parser.add_argument("--freq_tgt", type=float, required=True, help="感兴趣频率 (Hz)")
    parser.add_argument("--freq_lifetime", type=float, required=True, help="计算寿命的频率 (Hz)")
    parser.add_argument("--freq_width_tgt", type=float, required=True, help="感兴趣频率宽度 (Hz)")
    parser.add_argument("--amp_threshold", type=float, default=0.005, help="幅度阈值")
    parser.add_argument("--z_min", type=float, default=None, help="Z轴最小值")
    parser.add_argument("--z_max", type=float, default=None, help="Z轴最大值")

    parser.add_argument("--h2", type=str, default="h", help="TH2F 名称")
    parser.add_argument("--h1", type=str, default="h_proj", help="TH1F 名称")
    parser.add_argument(
        "--correct-frequency",
        action="store_true",
        default=False,
        help="是否修正频率（默认: False）"
    )
    
    parser.add_argument(
        "--no-correct-frequency",
        action="store_false",
        dest="correct_frequency",
        help="不修正频率"
    )
    args = parser.parse_args()
    
    # 处理 logz 参数：--logz 优先，但如果同时指定了 --no-logz，则禁用
    if args.no_logz:
        use_logz = False
    else:
        use_logz = args.logz
    
    print(f"Z 轴对数显示: {'启用' if use_logz else '禁用'}")

    # ====================== 设置图片输出目录 ======================
    plot_dir = Path(args.plot_dir)
    plot_dir.mkdir(exist_ok=True)
    print(f"图片将保存到目录: {plot_dir}/")

    input_dirs = args.dir
    output_file = args.output
    hist2d_name = args.h2
    hist1d_name = args.h1

    log_file = Path(output_file).with_suffix('.txt')
    processing_log = []
    header = "文件名\t初始中心\t初始sigma\t初始峰高\t拟合μ\tμ误差\t拟合A\tA误差\t拟合σ\tσ误差\tChi2\tNDF\tChi2/NDF\t参数来源\tlifetime"
    processing_log.append(header)

    print(f"开始处理，共 {len(input_dirs)} 个目录...\n")

    all_root_files = []
    for d in input_dirs:
        dir_path = Path(d)
        if not dir_path.exists() or not dir_path.is_dir():
            continue
        root_files = sorted(dir_path.glob("*.root"))
        all_root_files.extend(root_files)

    if not all_root_files:
        print("错误：未找到任何 .root 文件！")
        sys.exit(1)


    sum_h1 = None          # 原始 h1 的累加
    sum_h2 = None          # 原始 h2 的累加
    sum_h1_corrected = None   # 修正后 h1 的累加
    sum_h2_corrected = None   # 修正后 h2 的累加
    
    for i, fpath in enumerate(all_root_files, 1):
        print(f"[{i:3d}/{len(all_root_files)}] 处理: {fpath.name}")
        
        f = ROOT.TFile.Open(str(fpath), "UPDATE")
        if not f or f.IsZombie():
            continue
    
        h2 = f.Get(hist2d_name)
        
        if isinstance(h2, ROOT.TH2F):
            # 第一步：计算 lifetime（使用你已有的函数）
            lifetime, proj, status = calculate_lifetime_from_h2(
                h2=h2,
                freq_tgt=args.freq_lifetime,
                freq_width_tgt=args.freq_width_tgt,
                amp_threshold=0.2
            )
            # 第二步：从 lifetime + 0.1 ~ lifetime + 0.2 截取并投影到 X 轴
            if lifetime is not None:
                h1, y_low, y_high = create_h1_from_lifetime_window(
                        h2=h2,
                        lifetime=lifetime,
                        window_offset=args.t_min,   # lifetime + 0.1
                        window_width=args.t_max - args.t_min     # 宽度 0.1s → lifetime+0.1 ~ lifetime+0.2
                    )
                
        if isinstance(h1, ROOT.TH1):
            fit_func, h1_corrected, h2_corrected = perform_gaussian_fit_and_plot(
                h1=h1,
                h2=h2,
                hist_name=f"{fpath.stem}_{hist1d_name}",
                processing_log=processing_log,
                original_filename=fpath.stem,
                plot_dir=plot_dir,
                freq_tgt=args.freq_tgt,
                freq_width_tgt=args.freq_width_tgt,
                t_min=args.t_min,
                t_max=args.t_max,
                freq_low=args.freq_low,
                freq_high=args.freq_high,
                amp_threshold=args.amp_threshold,
                z_min=args.z_min,
                z_max=args.z_max,
                correct_frequency=args.correct_frequency,
                lifetime=lifetime,
                logz=use_logz,
                skip_low_peak_check=not args.correct_frequency  # 新增：当不修正频率时跳过检查
            )
            
            # ====================== 原始直方图叠加 ======================
            if isinstance(h1, ROOT.TH1):
                if sum_h1 is None:
                    sum_h1 = h1.Clone("h_proj_sum_original")
                    sum_h1.SetDirectory(0)
                    sum_h1.Reset()
                sum_h1.Add(h1)
    
            if isinstance(h2, ROOT.TH2):
                if sum_h2 is None:
                    sum_h2 = h2.Clone("h2_sum_original")
                    sum_h2.SetDirectory(0)
                    sum_h2.Reset()
                sum_h2.Add(h2)
    
            # ====================== 修正后直方图叠加 ======================
            if h1_corrected is not None:
                if sum_h1_corrected is None:
                    sum_h1_corrected = h1_corrected.Clone("h_proj_sum_corrected")
                    sum_h1_corrected.SetDirectory(0)
                    sum_h1_corrected.Reset()
                sum_h1_corrected.Add(h1_corrected)
    
            if isinstance(h2_corrected, ROOT.TH2):
                if sum_h2_corrected is None:
                    sum_h2_corrected = h2_corrected.Clone("h2_sum_corrected")
                    sum_h2_corrected.SetDirectory(0)
                    sum_h2_corrected.Reset()
                sum_h2_corrected.Add(h2_corrected)
    
        f.Close()

    print("正在绘制累加后的总谱 (sum_h1 / sum_h2 vs corrected)...")
    #t_min=args.t_min + lifetime
    #t_max=args.t_max + lifetime
    t_min=args.t_min
    t_max=args.t_max
    print("chenrj ...1 t_min ",t_min)
    freq_low=args.freq_low
    freq_high=args.freq_high
    freq_tgt=args.freq_tgt
    freq_width_tgt=args.freq_width_tgt
    amp_threshold=args.amp_threshold
    z_min=args.z_min
    z_max=args.z_max
    
    c_sum = ROOT.TCanvas("c_sum_total", "Total Sum Comparison (Original vs Corrected)", 1900, 1500)
    
    # 定义四个 Pad
    pad_lt = ROOT.TPad("pad_sum_lt", "sum_h2 original",  0.00, 0.50, 0.50, 1.00)
    pad_lb = ROOT.TPad("pad_sum_lb", "sum_h1 original",  0.00, 0.00, 0.50, 0.50)
    pad_rt = ROOT.TPad("pad_sum_rt", "sum_h2 corrected", 0.50, 0.50, 1.00, 1.00)
    pad_rb = ROOT.TPad("pad_sum_rb", "sum_h1 corrected", 0.50, 0.00, 1.00, 0.50)
    
    for pad in [pad_lt, pad_lb, pad_rt, pad_rb]:
        c_sum.cd()
        pad.SetLeftMargin(0.13)
        pad.SetRightMargin(0.15)
        pad.SetBottomMargin(0.2 if pad in [pad_lb, pad_rb] else 0.20)
        pad.SetTopMargin(0.10)
        pad.Draw()
    
    # ====================== 左上：sum_h2 (原始) ======================
    pad_lt.cd()
    if sum_h2 and isinstance(sum_h2, ROOT.TH2):
        sum_h2.SetTitle("Sum of All TH2F - Original")
        sum_h2.SetStats(0)
        sum_h2.GetXaxis().SetNdivisions(505)
        if freq_low and freq_high:
            sum_h2.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
        sum_h2.Draw("COLZ")
        if use_logz:  # 使用 logz 参数控制
            pad_lt.SetLogz(True)
        set_axis_style(sum_h2)
        
        if z_min is not None: sum_h2.SetMinimum(z_min)
        if z_max is not None: sum_h2.SetMaximum(z_max)
        
        # 绿色频率辅助线
        if freq_low and freq_high:
            print("chenrj 2 ... t_min = ",t_min)
            line_t_min = ROOT.TLine(freq_low/1e6, t_min,  freq_high/1e6, t_min)
            line_t_max = ROOT.TLine(freq_low/1e6, t_max,  freq_high/1e6, t_max)
            line_t_min.SetLineColor(ROOT.kGreen); line_t_min.SetLineStyle(2); line_t_min.SetLineWidth(2); line_t_min.Draw()
            line_t_max.SetLineColor(ROOT.kGreen); line_t_max.SetLineStyle(2); line_t_max.SetLineWidth(2); line_t_max.Draw()
    
    # ====================== 左下：sum_h1 (原始) ======================
    pad_lb.cd()
    if sum_h1 and isinstance(sum_h1, ROOT.TH1):
        sum_h1.SetLineColor(ROOT.kBlue)
        sum_h1.SetLineWidth(2)
        sum_h1.SetTitle("Sum of All TH1F - Original;Frequency [MHz];Counts")
        sum_h1.GetXaxis().SetNdivisions(505)
        if freq_low and freq_high:
            sum_h1.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
        sum_h1.Draw("HIST")
        sum_h1.GetYaxis().SetRangeUser(0,0.5)
        sum_h1.SetLineColor(1)
    # ====================== 右上：sum_h2_corrected ======================
    pad_rt.cd()
    if sum_h2_corrected and isinstance(sum_h2_corrected, ROOT.TH2):
        sum_h2_corrected.SetTitle("Sum of All TH2F - Frequency Corrected")
        sum_h2_corrected.SetStats(0)
        sum_h2_corrected.GetXaxis().SetNdivisions(505)
        if freq_low and freq_high:
            sum_h2_corrected.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
        sum_h2_corrected.Draw("COLZ")
        if use_logz:  # 使用 logz 参数控制
            pad_rt.SetLogz(True)
        set_axis_style(sum_h2_corrected)
        
        if z_min is not None: sum_h2_corrected.SetMinimum(z_min)
        if z_max is not None: sum_h2_corrected.SetMaximum(z_max)
        line_t_min.Draw()
        line_t_max.Draw()
    # ====================== 右下：sum_h1_corrected ======================
    pad_rb.cd()
    if sum_h1_corrected and isinstance(sum_h1_corrected, ROOT.TH1):
        sum_h1_corrected.SetLineColor(ROOT.kRed)      # 用红色突出修正后
        sum_h1_corrected.SetLineWidth(2)
        sum_h1_corrected.SetTitle("Sum of All TH1F - Frequency Corrected;Frequency [MHz];Counts")
        sum_h1_corrected.GetXaxis().SetNdivisions(505)
        if freq_low and freq_high:
            sum_h1_corrected.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
        sum_h1_corrected.Draw("HIST")
        sum_h1_corrected.SetLineColor(1)
        sum_h1_corrected.GetYaxis().SetRangeUser(0,0.5)
        
        fit_sum_h1_corrected, result_sum_h1_corrected = fit_single_histogram(sum_h1_corrected, 
            hist_name="sum_h1_corrected",
            freq_tgt=args.freq_tgt,
            freq_width_tgt=args.freq_width_tgt,
            color=ROOT.kBlue)
        
        if fit_sum_h1_corrected:
            fit_sum_h1_corrected.Draw("samel")
            fit_sum_h1_corrected.GetXaxis().SetRangeUser(freq_low/1e6, freq_high/1e6)
            
    # ====================== 图例和信息 ======================
    pad_rb.cd()   # 在右下添加图例
    legend = ROOT.TLegend(0.60, 0.75, 0.88, 0.88)
    legend.AddEntry(sum_h1_corrected,  f"t=[{t_min} ,{t_max}] s",  "l")
    legend.Draw()
    
    # 更新并保存图片
    c_sum.cd()
    c_sum.Modified()
    c_sum.Update()
    
    png_sum_path = plot_dir / "sum_total_comparison_2x2.png"
    c_sum.SaveAs(str(png_sum_path))
    print(f" → 总谱对比图已保存: {png_sum_path.name}")
    

    
    # ====================== 保存 ROOT 文件 ======================
    out = ROOT.TFile(output_file, "RECREATE")
    if sum_h2:
        sum_h2.Write()
    if sum_h1:
        sum_h1.Write()
    
    if sum_h2_corrected:
        sum_h2_corrected.Write()
    if sum_h1_corrected:
        sum_h1_corrected.Write()
    c_sum.Write()
    out.Close()
    c_sum.Close()    
    
    print("叠加完成并保存：")
    print("   - h_proj_sum_original     (原始 h1 叠加)")
    print("   - h2_sum_original         (原始 h2 叠加)")
    print("   - h_proj_sum_corrected    (修正后 h1 叠加)")
    print("   - h2_sum_corrected        (修正后 h2 叠加)")

    # 保存表格日志
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            for line in processing_log:
                f.write(line + "\n")
        print(f"\n✓ 表格已保存到: {log_file}")
        print(f"   图片文件夹: {plot_dir}/")
    except Exception as e:
        print(f"警告：保存日志失败: {e}")

    print("\n处理完成！")


if __name__ == "__main__":
    main()