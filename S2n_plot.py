import ROOT
import sys
from array import array
import argparse


def main():
    parser = argparse.ArgumentParser(description="AME2020 S2n vs N Plot (Three Layers)")
    parser.add_argument("-f", "--file", type=str, default="mass_1.mas20.txt",
                        help="Path to AME2020 mass file")
    parser.add_argument("--expfile", type=str, default="mass_exp.txt",
                        help="Your experimental mass file (Z A ME_EXP ER_EXP)")
    parser.add_argument("--zmin", type=int, default=70, help="Minimum Z")
    parser.add_argument("--zmax", type=int, default=82, help="Maximum Z")
    parser.add_argument("--nmin", type=int, default=100, help="Minimum N")
    parser.add_argument("--nmax", type=int, default=140, help="Maximum N")
    parser.add_argument("--s2nmin", type=float, default=0.0, help="Minimum S2n (MeV)")
    parser.add_argument("--s2nmax", type=float, default=22.0, help="Maximum S2n (MeV)")
 
    args = parser.parse_args()

    ame_file = args.file
    exp_file = args.expfile
    Z_min = args.zmin
    Z_max = args.zmax
    N_min = args.nmin
    N_max = args.nmax
    S2n_min = args.s2nmin
    S2n_max = args.s2nmax

    print("=== AME2020 S2n vs N Plot (Three Layers) ===")
    print(f"AME File      : {ame_file}")
    print(f"Exp Data File : {exp_file}\n")

    # ====================== Read AME2020 (with Element Symbol) ======================
    ame_data = {}
    element = {}          # Z -> EL (e.g. Pb, Bi, ...)
    neutron_me = None

    with open(ame_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if len(line) < 100: continue
            try:
                N = int(line[4:9].strip())
                Z = int(line[9:14].strip())
                me_str = line[28:43].strip()
                unc_str = line[43:55].strip()
                el = line[20:24].strip()          # ← 元素符号

                is_theo = ('#' in me_str) or ('*' in me_str)
                me_clean = me_str.replace('#', '').replace('*', '').strip()
                if not me_clean: continue
                mass_exc = float(me_clean)
                unc = float(unc_str.replace('#','').replace('*','').strip()) if unc_str.strip() else 0.0

                ame_data[(N, Z)] = {'mass_exc': mass_exc, 'unc': unc, 'theo': is_theo}
                
                # 保存元素符号（每个 Z 只保存一次）
                if Z not in element:
                    element[Z] = el

                if N == 1 and Z == 0:
                    neutron_me = mass_exc
            except:
                continue

    # ====================== Read Experimental Data ======================
    exp_mass = {}
    with open(exp_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('Z'): continue
            parts = line.split()
            if len(parts) < 4: continue
            try:
                Z = int(parts[0])
                A = int(parts[1])
                ME = float(parts[2])
                ER = float(parts[3])
                N = A - Z
                exp_mass[(N, Z)] = (ME, ER)
            except:
                continue

    print(f"AME nuclei: {len(ame_data)} | Experimental nuclei: {len(exp_mass)}")

    # ====================== ROOT Plot ======================
    ROOT.gROOT.SetStyle("Plain")
    ROOT.gStyle.SetOptStat(0)

    c = ROOT.TCanvas("c_S2n", "S2n vs N", 1600, 1000)
    c.SetMargin(0.13, 0.08, 0.13, 0.10)

    mg = ROOT.TMultiGraph()
    leg = ROOT.TLegend(0.7859825,0.3676622,0.979975,0.8856849)
    leg.SetFillStyle(0)
    leg.SetBorderSize(0)

    colors = [2,3,4,6,7,8,9,28,30,38,41,42,43,44,46,47,48,49]

    for z in range(Z_max, Z_min - 1,-1):
        n_all = array('d')
        s2n_all = array('d')
        n_black = array('d')
        s2n_black = array('d')
        err_black = array('d')
        n_red = array('d')
        s2n_red = array('d')
        err_red = array('d')

        for n in range(N_min, N_max + 1):
            key = (n, z)
            key_prev = (n-2, z)

            # 1. All AME (colored dashed)
            if key in ame_data and key_prev in ame_data:
                s2n = (ame_data[key_prev]['mass_exc'] - ame_data[key]['mass_exc'] + 2*neutron_me) / 1000.0
                if S2n_min <= s2n <= S2n_max:
                    n_all.append(float(n))
                    s2n_all.append(s2n)

            # 2. AME non-# (black)
            if (key in ame_data and not ame_data[key]['theo'] and
                key_prev in ame_data and not ame_data[key_prev]['theo']):
                s2n = (ame_data[key_prev]['mass_exc'] - ame_data[key]['mass_exc'] + 2*neutron_me) / 1000.0
                unc = ((ame_data[key_prev]['unc']**2 + ame_data[key]['unc']**2)**0.5) / 1000.0
                if S2n_min <= s2n <= S2n_max:
                    n_black.append(float(n))
                    s2n_black.append(s2n)
                    err_black.append(unc)

            # 3. RED: Current ONLY from exp, N-2 from exp or AME non-#
            if key in exp_mass:
                mass_curr, unc_curr = exp_mass[key]
                mass_prev = unc_prev = None
                if key_prev in exp_mass:
                    mass_prev, unc_prev = exp_mass[key_prev]
                elif (key_prev in ame_data and not ame_data[key_prev]['theo']):
                    mass_prev = ame_data[key_prev]['mass_exc']
                    unc_prev = ame_data[key_prev]['unc']

                if mass_prev is not None:
                    s2n = (mass_prev - mass_curr + 2*neutron_me) / 1000.0
                    unc = ((unc_prev**2 + unc_curr**2)**0.5) / 1000.0
                    if S2n_min <= s2n <= S2n_max:
                        n_red.append(float(n))
                        s2n_red.append(s2n)
                        err_red.append(unc)

        if len(n_all) == 0:
            continue

        col = colors[(Z_max - 2 - z) % len(colors)]
        el = element.get(z, f"Z{z}")   # 获取元素符号

        # Colored dashed line
        gr_all = ROOT.TGraph(len(n_all), n_all, s2n_all)
        gr_all.SetLineColor(col)
        gr_all.SetLineStyle(2)
        gr_all.SetLineWidth(2)
        mg.Add(gr_all, "L")
        if (z - Z_min) < 15:
            leg.AddEntry(gr_all, f"Z={z} {el}", "L")

        # Black - AME non-#
        if len(n_black) > 0:
            gr_black = ROOT.TGraphErrors(len(n_black), n_black, s2n_black,
                                         array('d',[0]*len(n_black)), err_black)
            gr_black.SetMarkerStyle(24)
            gr_black.SetMarkerSize(2)
            gr_black.SetMarkerColor(1)
            gr_black.SetLineColor(1)
            mg.Add(gr_black, "LP")
            if z == Z_min:
                leg.AddEntry(gr_black, "AME non-#", "P")

        # Red points - per Z color + Element symbol
        if len(n_red) > 0:
            gr_red = ROOT.TGraphErrors(len(n_red), n_red, s2n_red,
                                       array('d',[0]*len(n_red)), err_red)
            gr_red.SetMarkerStyle(21)
            gr_red.SetMarkerSize(1.3)
            gr_red.SetMarkerColor(col)
            gr_red.SetLineColor(col)
            mg.Add(gr_red, "LP")
            leg.AddEntry(gr_red, f"Z={z} {el} (Exp)", "P")   # ← 显示元素符号

    # Final Plot
    mg.Draw("A")
    mg.GetXaxis().SetTitle("Neutron Number N")
    mg.GetYaxis().SetTitle("S_{2n} (MeV)")
    mg.GetXaxis().SetRangeUser(N_min, N_max)
    mg.GetYaxis().SetRangeUser(S2n_min, S2n_max)
    mg.SetTitle(f"S_{{2n}} vs N (Z={Z_min}-{Z_max}); N; S_{{2n}} (MeV)")

    leg.Draw()
    c.Update()

    # Save
    root_name = f"S2n_vs_N_Z{Z_min}-{Z_max}.root"
    root_file = ROOT.TFile(root_name, "RECREATE")
    c.Write("c_S2n")
    mg.Write("mg_S2n")
    root_file.Close()

    c.SaveAs(f"S2n_vs_N_Z{Z_min}-{Z_max}.png")
    c.SaveAs(f"S2n_vs_N_Z{Z_min}-{Z_max}.pdf")

    print(f"\n🎉 Plot completed! Legend now shows element symbols (e.g. Pb, Bi).")


if __name__ == "__main__":
    main()