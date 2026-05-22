import ROOT
import sys
import argparse

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='分析 ROOT 文件中的 2D 直方图，投影并拟合高斯峰')
    parser.add_argument('filename', type=str, help='ROOT 文件名')
    parser.add_argument('histname', type=str, help='2D 直方图名称')
    
    # y 轴投影范围参数（使用实际数值）
    parser.add_argument('--ymin', type=float, required=True, help='投影的 y 轴最小值')
    parser.add_argument('--ymax', type=float, required=True, help='投影的 y 轴最大值')
    
    # 拟合范围参数
    parser.add_argument('--gmin', type=float, required=True, help='基态拟合左边界')
    parser.add_argument('--gmax', type=float, required=True, help='基态拟合右边界')
    parser.add_argument('--emin', type=float, required=True, help='激发态拟合左边界')
    parser.add_argument('--emax', type=float, required=True, help='激发态拟合右边界')
    
    # 本底范围参数
    parser.add_argument('--bkmin', type=float, required=True, help='本底拟合左边界')
    parser.add_argument('--bkmax', type=float, required=True, help='本底拟合右边界')
    
    # 显示范围参数
    parser.add_argument('--xmin', type=float, default=None, help='x 轴显示范围最小值')
    parser.add_argument('--xmax', type=float, default=None, help='x 轴显示范围最大值')
    parser.add_argument('--zmin', type=float, default=None, help='z 轴显示范围最小值')
    parser.add_argument('--zmax', type=float, default=None, help='z 轴显示范围最大值')
    
    args = parser.parse_args()
    
    # 1. 打开文件并读取直方图
    file = ROOT.TFile.Open(args.filename, "READ")
    if not file or file.IsZombie():
        print(f"Error: Cannot open file {args.filename}")
        sys.exit(1)

    h2 = file.Get(args.histname)
    if not h2 or not h2.InheritsFrom("TH2"):
        print(f"Error: Cannot find {args.histname} or not a 2D histogram")
        sys.exit(1)
    
    print(f"读取: {args.filename} -> {args.histname}")
    
    # 2. 将y轴数值范围转换为bin编号
    ybinmin = h2.GetYaxis().FindBin(args.ymin)
    ybinmax = h2.GetYaxis().FindBin(args.ymax)
    
    # 确保边界正确
    if args.ymin > h2.GetYaxis().GetBinLowEdge(ybinmin):
        ybinmin += 1
    if args.ymax < h2.GetYaxis().GetBinUpEdge(ybinmax):
        ybinmax -= 1
    
    if ybinmin > ybinmax or ybinmin < 1 or ybinmax > h2.GetNbinsY():
        print(f"Error: Invalid y range [{args.ymin}, {args.ymax}]")
        sys.exit(1)
    
    print(f"Y范围: [{args.ymin}, {args.ymax}] -> bins [{ybinmin}, {ybinmax}]")
    
    # 3. 设置显示范围
    h2_display = h2.Clone("h2_display")
    if args.xmin or args.xmax:
        xmin = args.xmin if args.xmin else h2_display.GetXaxis().GetXmin()
        xmax = args.xmax if args.xmax else h2_display.GetXaxis().GetXmax()
        h2_display.GetXaxis().SetRangeUser(xmin, xmax)
    if args.zmin:
        h2_display.SetMinimum(args.zmin)
    if args.zmax:
        h2_display.SetMaximum(args.zmax)
    
    # 4. 投影到x轴
    proj = h2_display.ProjectionX("proj", ybinmin, ybinmax)
    proj.SetTitle(f"X Projection (y=[{args.ymin:.2f}, {args.ymax:.2f}]);X axis;Counts")
    if args.xmin or args.xmax:
        proj.GetXaxis().SetRangeUser(xmin, xmax)
    
    # 5. 计算本底水平（在指定的本底范围内取平均值）
    bkmin_bin = proj.GetXaxis().FindBin(args.bkmin)
    bkmax_bin = proj.GetXaxis().FindBin(args.bkmax)
    if bkmin_bin < 1:
        bkmin_bin = 1
    if bkmax_bin > proj.GetNbinsX():
        bkmax_bin = proj.GetNbinsX()
    
    # 计算本底平均值
    bk_sum = 0
    bk_count = 0
    for i in range(bkmin_bin, bkmax_bin + 1):
        bk_sum += proj.GetBinContent(i)
        bk_count += 1
    background_level = bk_sum / bk_count if bk_count > 0 else 0
    print(f"本底范围: [{args.bkmin}, {args.bkmax}] -> 平均本底 = {background_level:.2f}")
    
    # 6. 对基态和激发态范围投影到y轴（原始数据）
    gxmin = h2.GetXaxis().FindBin(args.gmin)
    gxmax = h2.GetXaxis().FindBin(args.gmax)
    proj_y_gs_raw = h2.ProjectionY("proj_y_gs_raw", gxmin, gxmax)
    proj_y_gs_raw.SetTitle(f"Y Projection - Ground State (raw);Y axis;Counts")
    
    exmin = h2.GetXaxis().FindBin(args.emin)
    exmax = h2.GetXaxis().FindBin(args.emax)
    proj_y_ex_raw = h2.ProjectionY("proj_y_ex_raw", exmin, exmax)
    proj_y_ex_raw.SetTitle(f"Y Projection - Excited State (raw);Y axis;Counts")
    
    # 7. 扣本底后的投影
    proj_y_gs = proj_y_gs_raw.Clone("proj_y_gs")
    proj_y_ex = proj_y_ex_raw.Clone("proj_y_ex")
    
    # 扣除本底
    for i in range(1, proj_y_gs.GetNbinsX() + 1):
        content = proj_y_gs.GetBinContent(i)
        proj_y_gs.SetBinContent(i, max(0, content - background_level))
        proj_y_gs.SetBinError(i, proj_y_gs_raw.GetBinError(i))
    
    for i in range(1, proj_y_ex.GetNbinsX() + 1):
        content = proj_y_ex.GetBinContent(i)
        proj_y_ex.SetBinContent(i, max(0, content - background_level))
        proj_y_ex.SetBinError(i, proj_y_ex_raw.GetBinError(i))
    
    proj_y_gs.SetTitle(f"Y Projection - Ground State (bg subtracted);Y axis;Counts")
    proj_y_ex.SetTitle(f"Y Projection - Excited State (bg subtracted);Y axis;Counts")
    
    # 8. 独立拟合（使用扣本底前的投影）
    gaussian_gs = ROOT.TF1("gaussian_gs", "gaus", args.gmin, args.gmax)
    gaussian_ex = ROOT.TF1("gaussian_ex", "gaus", args.emin, args.emax)
    
    proj.Fit(gaussian_gs, "SR+", "", args.gmin, args.gmax)
    proj.Fit(gaussian_ex, "SR+", "", args.emin, args.emax)
    gaussian_gs.SetLineColor(3)
    gaussian_ex.SetLineColor(4)
    
    gs_amp = gaussian_gs.GetParameter(0)
    gs_mean = gaussian_gs.GetParameter(1)
    gs_sigma = abs(gaussian_gs.GetParameter(2))
    gs_area = gs_amp * gs_sigma * ROOT.TMath.Sqrt(2 * ROOT.TMath.Pi())
    
    ex_amp = gaussian_ex.GetParameter(0)
    ex_mean = gaussian_ex.GetParameter(1)
    ex_sigma = abs(gaussian_ex.GetParameter(2))
    ex_area = ex_amp * ex_sigma * ROOT.TMath.Sqrt(2 * ROOT.TMath.Pi())
    
    # 9. 总拟合（两个高斯 + 常数本底）
    fit_min = min(args.gmin, args.emin)
    fit_max = max(args.gmax, args.emax)
    
    total_func = ROOT.TF1("total_func", 
        "[0] + [1]*exp(-0.5*((x-[2])/[3])**2) + [4]*exp(-0.5*((x-[5])/[6])**2)", 
        fit_min, fit_max)
    
    total_func.SetParameters(background_level, gs_amp, gs_mean, gs_sigma, ex_amp, ex_mean, ex_sigma)
    total_func.SetParLimits(2, gs_mean-0.01, gs_mean+0.01)
    total_func.SetParLimits(5, ex_mean-0.01, ex_mean+0.01)
    proj.Fit(total_func, "SR", "", fit_min, fit_max)
    
    const_bg = total_func.GetParameter(0)
    gs_area_total = total_func.GetParameter(1) * abs(total_func.GetParameter(3)) * ROOT.TMath.Sqrt(2 * ROOT.TMath.Pi())
    ex_area_total = total_func.GetParameter(4) * abs(total_func.GetParameter(6)) * ROOT.TMath.Sqrt(2 * ROOT.TMath.Pi())
    ratio = ex_area_total / gs_area_total if gs_area_total != 0 else 0
    yield_ex = ex_area_total / (gs_area_total + ex_area_total) if (gs_area_total + ex_area_total) != 0 else 0
    
    # 10. 对扣本底后的激发态Y投影进行指数拟合
    exp_func = ROOT.TF1("exp_func", "[0]*exp([1]*x)", 
                        proj_y_ex.GetXaxis().GetXmin(), proj_y_ex.GetXaxis().GetXmax())
    exp_func.SetParameters(proj_y_ex.GetMaximum(), -0.1)
    proj_y_ex.Fit(exp_func, "SR")
    
    exp_amp = exp_func.GetParameter(0)
    exp_decay = exp_func.GetParameter(1)
    
    print(f"\n本底水平: {background_level:.2f}")
    print(f"基态: 中心={gs_mean:.6f}, sigma={gs_sigma:.6f}, 面积={gs_area:.6f}")
    print(f"激发态: 中心={ex_mean:.6f}, sigma={ex_sigma:.6f}, 面积={ex_area:.6f}")
    print(f"总拟合: 本底={const_bg:.6f}, 比例={ratio:.6f}, 产额={yield_ex:.6f}")
    print(f"指数拟合: 幅度={exp_amp:.6f}, 衰减常数={exp_decay:.6f}")
    
    # 11. 保存结果到文本文件
    output_txt = f"{args.histname}_results_y{args.ymin}_{args.ymax}.txt"
    with open(output_txt, "w") as f:
        f.write("# Fit Results\n")
        f.write(f"Filename: {args.filename}\n")
        f.write(f"Histogram: {args.histname}\n")
        f.write(f"Y projection range: [{args.ymin}, {args.ymax}]\n")
        f.write(f"Background range: [{args.bkmin}, {args.bkmax}]\n")
        f.write(f"Background level: {background_level:.2f}\n\n")
        
        f.write("="*50 + "\n")
        f.write("Total Fit (2 Gaussians + Constant Background)\n")
        f.write("="*50 + "\n")
        f.write(f"Constant Background: {const_bg:.2f}\n\n")
        
        f.write("Ground State:\n")
        f.write(f"  Fit range: [{args.gmin}, {args.gmax}]\n")
        f.write(f"  Mean: {total_func.GetParameter(2):.6f}\n")
        f.write(f"  Sigma: {abs(total_func.GetParameter(3)):.6f}\n")
        f.write(f"  Area: {gs_area_total:.1f}\n\n")
        
        f.write("Excited State:\n")
        f.write(f"  Fit range: [{args.emin}, {args.emax}]\n")
        f.write(f"  Mean: {total_func.GetParameter(5):.6f}\n")
        f.write(f"  Sigma: {abs(total_func.GetParameter(6)):.6f}\n")
        f.write(f"  Area: {ex_area_total:.1f}\n\n")
        
        f.write(f"Ratio (ex/gs): {ratio:.6f}\n")
        f.write(f"Excited State Yield: {yield_ex:.6f}\n\n")
        
        f.write("="*50 + "\n")
        f.write("Exponential Fit for Excited State Y Projection (bg subtracted)\n")
        f.write("="*50 + "\n")
        f.write(f"Function: [0]*exp([1]*x)\n")
        f.write(f"Amplitude: {exp_amp:.2f}\n")
        f.write(f"Decay constant: {exp_decay:.6f}\n")
        
        t1_2 = ROOT.TMath.Log(2) / abs(exp_decay)
        f.write(f"Half-life T1/2: {t1_2:.4f}\n")
    
    print(f"已保存: {output_txt}")
    
    # 12. 绘制综合画布
    c1 = ROOT.TCanvas("c1", "Analysis", 1200, 900)
    c1.Divide(2, 2)
    
    # 2D直方图
    c1.cd(1)
    ROOT.gPad.SetTopMargin(0.001)
    ROOT.gPad.SetBottomMargin(0.12)
    ROOT.gPad.SetLeftMargin(0.12)
    ROOT.gPad.SetRightMargin(0.15)
    h2_display.Draw("COLZ")
    h2_display.SetTitle("")
    
    y_low = h2.GetYaxis().GetBinLowEdge(ybinmin)
    y_high = h2.GetYaxis().GetBinUpEdge(ybinmax)
    xmin_disp = args.xmin if args.xmin else h2_display.GetXaxis().GetXmin()
    xmax_disp = args.xmax if args.xmax else h2_display.GetXaxis().GetXmax()
    
    # 绘制投影y范围框
    box = ROOT.TBox(xmin_disp, y_low, xmax_disp, y_high)
    box.SetFillColor(ROOT.kRed)
    box.SetFillStyle(3001)
    box.Draw()
    
    # 绘制本底范围框
    bk_low = proj.GetXaxis().GetBinLowEdge(bkmin_bin)
    bk_high = proj.GetXaxis().GetBinUpEdge(bkmax_bin)
    bk_box = ROOT.TBox(bk_low, y_low, bk_high, y_high)
    bk_box.SetFillColor(ROOT.kBlue)
    bk_box.SetFillStyle(3002)
    bk_box.SetLineColor(ROOT.kBlue)
    bk_box.SetLineStyle(2)
    bk_box.Draw()
    
    # 获取当前显示的Y轴范围
    y_min_display = h2_display.GetYaxis().GetXmin()
    y_max_display = h2_display.GetYaxis().GetXmax()
    
    # 创建指示线
    line_emin = ROOT.TLine(args.emin, y_min_display, args.emin, y_max_display)
    line_emax = ROOT.TLine(args.emax, y_min_display, args.emax, y_max_display)
    line_gmin = ROOT.TLine(args.gmin, y_min_display, args.gmin, y_max_display)
    line_gmax = ROOT.TLine(args.gmax, y_min_display, args.gmax, y_max_display)
    line_bkmin = ROOT.TLine(args.bkmin, y_min_display, args.bkmin, y_max_display)
    line_bkmax = ROOT.TLine(args.bkmax, y_min_display, args.bkmax, y_max_display)
    
    for line in [line_gmin, line_gmax]:
        line.SetLineColor(ROOT.kRed)
        line.SetLineWidth(2)
        line.SetLineStyle(2)
        line.Draw()
    for line in [line_emin, line_emax]:
        line.SetLineColor(ROOT.kBlue)
        line.SetLineWidth(2)
        line.SetLineStyle(2)
        line.Draw()
    
    line_bkmin.SetLineColor(6)
    line_bkmin.SetLineWidth(2)
    line_bkmin.SetLineStyle(2)
    line_bkmin.Draw()
    line_bkmax.SetLineColor(6)
    line_bkmax.SetLineWidth(2)
    line_bkmax.SetLineStyle(2)
    line_bkmax.Draw()
    
    # 添加标签
    latex = ROOT.TLatex()
    latex.SetTextColor(ROOT.kGreen)
    latex.SetTextSize(0.025)
    latex.DrawLatex(args.emin + 0.001, y_high - (y_high-y_low)*0.1, "Excited State")
    latex.DrawLatex(args.gmin + 0.001, y_high - (y_high-y_low)*0.05, "Ground State")
    latex.SetTextColor(ROOT.kBlue)
    latex.DrawLatex(args.bkmin + 0.001, y_low + (y_high-y_low)*0.02, "Background")
    
    # 基态Y投影（扣本底后）
    c1.cd(2)
    ROOT.gPad.SetTopMargin(0.001)
    ROOT.gPad.SetBottomMargin(0.12)
    ROOT.gPad.SetLeftMargin(0.12)
    ROOT.gPad.SetRightMargin(0.01)
    proj_y_gs.Draw()
    proj_y_gs.GetXaxis().SetTitle("Y axis")
    proj_y_gs.SetStats(0)
    proj_y_gs.SetLineColor(ROOT.kRed)
    proj_y_gs.SetLineWidth(2)
    
    # X投影和拟合
    c1.cd(3)
    ROOT.gPad.SetTopMargin(0.001)
    ROOT.gPad.SetBottomMargin(0.12)
    ROOT.gPad.SetLeftMargin(0.12)
    ROOT.gPad.SetRightMargin(0.15)
    
    proj.Draw()
    proj.GetXaxis().SetTitle("X axis [MHz]")
    proj.SetStats(0)
    total_func.SetLineColor(4)
    total_func.SetLineWidth(2)
    total_func.Draw("SAME")
    proj.SetTitle("")
    
    gs_comp = ROOT.TF1("gs_comp", f"[0]*exp(-0.5*((x-[1])/[2])**2)", fit_min, fit_max)
    gs_comp.SetParameters(total_func.GetParameter(1), total_func.GetParameter(2), total_func.GetParameter(3))
    gs_comp.SetLineColor(ROOT.kRed)
    gs_comp.SetLineStyle(2)
    gs_comp.SetLineWidth(2)
    gs_comp.Draw("SAME")
    
    ex_comp = ROOT.TF1("ex_comp", f"[0]*exp(-0.5*((x-[1])/[2])**2)", fit_min, fit_max)
    ex_comp.SetParameters(total_func.GetParameter(4), total_func.GetParameter(5), total_func.GetParameter(6))
    ex_comp.SetLineColor(ROOT.kBlue)
    ex_comp.SetLineStyle(2)
    ex_comp.SetLineWidth(2)
    ex_comp.Draw("SAME")
    
    # 绘制本底线
    bg_line = ROOT.TLine(fit_min, const_bg, fit_max, const_bg)
    bg_line.SetLineColor(ROOT.kGray)
    bg_line.SetLineStyle(3)
    bg_line.Draw()
    
    legend = ROOT.TLegend(0.55, 0.75, 0.95, 0.95)
    legend.AddEntry(total_func, f"Total Fit", "l")
    legend.AddEntry(gs_comp, f"Ground State (area={gs_area_total:.2e})", "l")
    legend.AddEntry(ex_comp, f"Excited State (area={ex_area_total:.2e})", "l")
    legend.AddEntry(bg_line, f"Background = {const_bg:.1f}", "l")
    legend.SetBorderSize(0)
    legend.Draw()
    
    # 获取总拟合的参数和误差
    gs_mean_total = total_func.GetParameter(2)
    gs_mean_error = total_func.GetParError(2)
    gs_sigma_total = abs(total_func.GetParameter(3))
    gs_sigma_error = total_func.GetParError(3)
    gs_area_total = total_func.GetParameter(1) * gs_sigma_total * ROOT.TMath.Sqrt(2 * ROOT.TMath.Pi())
    gs_area_error = gs_area_total * (abs(total_func.GetParError(1)/total_func.GetParameter(1)) + 
                                       abs(total_func.GetParError(3)/gs_sigma_total))
    
    ex_mean_total = total_func.GetParameter(5)
    ex_mean_error = total_func.GetParError(5)
    ex_sigma_total = abs(total_func.GetParameter(6))
    ex_sigma_error = total_func.GetParError(6)
    ex_area_total = total_func.GetParameter(4) * ex_sigma_total * ROOT.TMath.Sqrt(2 * ROOT.TMath.Pi())
    ex_area_error = ex_area_total * (abs(total_func.GetParError(4)/total_func.GetParameter(4)) + 
                                       abs(total_func.GetParError(6)/ex_sigma_total))
    
    # 计算面积比例及其误差
    ratio = ex_area_total / gs_area_total if gs_area_total != 0 else 0
    ratio_error = ratio * ((ex_area_error/ex_area_total)**2 + (gs_area_error/gs_area_total)**2)**0.5
    
    # 绘制文本信息
    text_info = ROOT.TLatex()
    text_info.SetTextSize(0.03)
    text_info.SetTextColor(ROOT.kBlack)
    
    text_info.DrawLatexNDC(0.12, 0.85, f"Ground State:")
    text_info.DrawLatexNDC(0.12, 0.80, f"  f = {gs_mean_total:.6f}#pm{gs_mean_error:.6f} [MHz]")
    text_info.DrawLatexNDC(0.12, 0.75, f"  Area = {gs_area_total:.1e}#pm{gs_area_error:.1e}")
    text_info.DrawLatexNDC(0.12, 0.68, f"Excited State:")
    text_info.DrawLatexNDC(0.12, 0.63, f"  f = {ex_mean_total:.6f}#pm{ex_mean_error:.6f} [MHz]")
    text_info.DrawLatexNDC(0.12, 0.58, f"  Area = {ex_area_total:.1e}#pm{ex_area_error:.1e}")
    text_info.DrawLatexNDC(0.12, 0.50, f"Area Ratio (ex/gs):")
    text_info.DrawLatexNDC(0.12, 0.45, f"  {ratio:.2e}#pm{ratio_error:.2e}")
    
    # 激发态Y投影和指数拟合（扣本底后）
    c1.cd(4)
    ROOT.gPad.SetTopMargin(0.001)
    ROOT.gPad.SetBottomMargin(0.12)
    ROOT.gPad.SetLeftMargin(0.12)
    ROOT.gPad.SetRightMargin(0.01)
    proj_y_ex.Draw()
    proj_y_ex.SetMinimum(0)  # 设置Y轴最小值为0
    proj_y_ex.GetXaxis().SetTitle("Y axis")
    proj_y_ex.SetStats(0)
    proj_y_ex.SetLineColor(ROOT.kBlue)
    proj_y_ex.SetLineWidth(2)
    exp_func.SetLineColor(ROOT.kRed)
    exp_func.SetLineWidth(2)
    exp_func.SetLineStyle(2)
    exp_func.Draw("SAME")
    
    legend2 = ROOT.TLegend(0.65, 0.75, 0.95, 0.88)
    legend2.AddEntry(proj_y_ex, "Data (bg subtracted)", "l")
    legend2.AddEntry(exp_func, f"Exponential Fit", "l")
    legend2.SetBorderSize(0)
    legend2.Draw()
    
    # 计算半衰期
    t1_2 = ROOT.TMath.Log(2) / abs(exp_decay)
    exp_decay_error = exp_func.GetParError(1)
    t1_2_error = t1_2 * (exp_decay_error / abs(exp_decay))
    
    text = ROOT.TLatex()
    text.SetTextSize(0.04)
    text.SetTextColor(ROOT.kRed)
    text.DrawLatexNDC(0.45, 0.85, f"T_{{1/2}} = {t1_2:.1f} #pm {t1_2_error:.1f} s")
    
    c1.Update()
    output_png = f"{args.histname}_analysis_y{args.ymin}_{args.ymax}.png"
    c1.SaveAs(output_png)
    print(f"\n已保存: {output_png}")
    
    file.Close()

if __name__ == "__main__":
    main()