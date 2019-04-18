################################################################
# SQUAD - superconducting quantum dot                          #
# Copyright (C) 2012-2019  Vladislav Pokorny; pokornyv@fzu.cz  #
# homepage: github.com/pokornyv/SQUAD                          #
# secondPT.py - second order perturbation theory solver        #
# method described in                                          #
#    Sci. Rep. 5, 8821 (2015).                                 #
#    Phys. Rev. B 93, 024523 (2016).                           #
################################################################

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from squadlib1 import *
from squadlib2 import *

t = time()
## printing header ########################################
ver = str(version_info[0])+'.'+str(version_info[1])+'.'+str(version_info[2])
if chat: 
	print('#'*100)
	print('# generated by '+str(argv[0])+', python version: '+str(ver)+\
	', SciPy version: '+str(sp.version.version))
	print('# '+ctime())
	print('# U ={0: .3f}, Delta ={1: .3f}, GammaR ={2: .3f}, GammaL ={3: .3f}, eps ={4: .3f}, Phi/pi ={5: .3f}'\
	.format(U,Delta,GammaR,GammaL,eps,P))
	print('# Kondo temperature (from Bethe ansatz): {0: .5e}'.format(KondoTemperature()))
	print('# energy axis: [{0: .5f} ..{1: .5f}], step ={2: .5f}, length ={3: 3d}'\
	.format(En_A[0],En_A[-1],dE,N))

## calculating the Hartree-Fock parameters ################
if chat: print('#\n# Calculating the Hartree-Fock solution:')
try:
	[n,mu,wzero,ErrMsgHF] = SolveHF()
except RuntimeError:
	print('#  Error: failed to calculate HF solution. Try changing the ABSinit_val parameter.')
	exit(0)

hfe = ed+U*n					## Hartree-Fock energy level
wzero = AndreevEnergy(hfe,mu)		## HF ABS frequencies

[GFn_A,GFa_A,ABSposGF1,ABSposGF2] = FillGreenHF(hfe,mu,wzero)
if Write_HFGF: WriteFile(GFn_A,GFa_A,wzero,'HF_green')
[ResGnp1,ResGnh1,ResGa1] = GFresidues(hfe,mu,-wzero) ## HF residues at -w0
[ResGnp2,ResGnh2,ResGa2] = GFresidues(hfe,mu, wzero) ## HF residues at +w0
IDin = IntDOS(GFn_A)

if chat: print('# - Hartree-Fock solution: n ={0: .5f}, mu ={1: .5f}, E(ABS) ={2: .5f}, int(DoS) ={3: .5f}'\
.format(n,mu,wzero,IDin))
if chat: print('# - HF residues: Gn: [{0: .5f}, {1: .5f}], Ga: [{2: .5f}, {3: .5f}]'\
.format(ResGnp1,ResGnp2,ResGa1,-ResGa1))

if chat: print('#\n# Calculating second-order PT solution:')

## bubbles and vertex ######################################
## two-particle bubble from HF
if chat: print('# - calculating two-particle bubbles...')
[Chin_A,Chia_A,ABSposChi1,ABSposChi2] = TwoParticleBubbles(GFn_A,GFa_A,wzero)
if Write_Bubble: WriteFile(Chin_A,Chia_A,En_A[ABSposChi1],'HF_bubbles')

## kernel of the Schwinger-Dyson equation (without the static HF parts U*n and U*mu)
ChiGamma_A = U**2*(Chin_A+Chia_A)

## dynamical self-energy ###################################
## solution of the Schwinger-Dyson equation
if chat: print('# - calculating dynamic self-energy...')
[Sigman_A,Sigmaa_A] = SelfEnergy(GFn_A,GFa_A,ChiGamma_A)
if Write_2ndSE: WriteFile(Sigman_A,Sigmaa_A,0.0,'2nd_SE')

## initial guess for the static part of self-energy ############
n  = ElectronDensity(n,mu,Sigman_A,Sigmaa_A)
mu = CooperPairDensity(n,mu,Sigman_A,Sigmaa_A)

## static self-energy ######################################
## the dynamic part is not changed anymore,
## charge consistency is aquired via shift of the static part
if chat: 
	print('#\n# Correcting the static self-energy:')
	if rootf == 'brentq': print("# - Using Brent's method")
	elif rootf == 'fixed_point': print("# - Using Steffensen's fixed point method")
n_old = 1e5
mu_old = 1e5
k = 1
while any([sp.fabs(n-n_old)>ConvN,sp.fabs(mu-mu_old)>ConvN]):
	n_old = n
	mu_old = mu
	if rootf == 'brentq':
		if eps == 0.0: n = 0.5 ## half-filling
		else: 
			eqnN = lambda x: x - ElectronDensity(x,mu,Sigman_A,Sigmaa_A)
			n = brentq(eqnN,0.0,1.0,xtol = ConvX)
		eqnA = lambda x: x - CooperPairDensity(n,x,Sigman_A,Sigmaa_A)
		## change upper and lower limits if needed
		mu = brentq(eqnA,MuMin,MuMax,xtol = ConvX)	
	elif rootf == 'fixed_point':
		## half-filling
		if eps == 0.0: n = 0.5 
		else: 			
			eqnN = lambda x: ElectronDensity(x,mu,Sigman_A,Sigmaa_A)
			n = fixed_point(eqnN,n_old,xtol = ConvX)
		eqnA = lambda x: CooperPairDensity(n,x,Sigman_A,Sigmaa_A)
		mu = fixed_point(eqnA,mu_old,xtol = ConvX)
	if chat: print('# - {0: 3d}:  n ={1: .5f}, mu ={2: .5f}'.format(k,n,mu))
	## update the HF energy
	hfe = ed + U*n 
	k += 1

## interacting Green's function #######
if chat: print('#\n# Calculating the interacting Green function...')
[GFn_A,GFa_A,Det_A,ABS_A,ABSpos_A,Res_A] = FillGreensFunction(n,mu,Sigman_A,Sigmaa_A)
wzeroInt = ABS_A[1] ## ABS energy
ABSposInt1 = ABSpos_A[0]
if Write_2ndGF: WriteFile(GFn_A,GFa_A,wzeroInt,'2nd_green')

## densities ##########################
n_final  = ElectronDensity(n,mu,Sigman_A,Sigmaa_A)
mu_final = CooperPairDensity(n,mu,Sigman_A,Sigmaa_A)
IDout = IntDOS(GFn_A)

## selfenergies at ABS ################
SEnABS = sp.real(Sigman_A[int(ABSpos_A[0])])
SEaABS = sp.real(Sigmaa_A[int(ABSpos_A[0])])

## Josephson current ##################
JC_A = JosephsonCurrent(GFa_A,Res_A[2],wzeroInt)
JC = JC_A[0]+JC_A[1]

## writing the results ################
if chat: 
	print('# - final densities: n ={0: .5f}, mu ={1: .5f}'.format(n_final,mu_final))
	print('# - 2ndPT Andreev energy: E(ABS) = {0: .5f}, int(DoS) = {1: .5f}'\
	.format(sp.fabs(wzeroInt),IDout))
	print('# - 2ndPT residues: Gn: [{0: .5f}, {1: .5f}], Ga: [{2: .5f}, {3: .5f}]'\
	.format(Res_A[0],Res_A[1],Res_A[2],Res_A[3]))
	if sp.sign(Res_A[2]*ResGa1) < 0.0:
		print('# Warning: Residue of anomalous function changes sign, {0: .5f} -> {1: .5f} (false pi-phase?)'\
		.format(ResGa1,Res_A[2]))
	if sp.fabs(Res_A[0]-Res_A[1]) > 1e-3 and eps == 0.0:
		print("# Warning: Residues of normal GF at ABS don't match.")
	print('# - self-energies at ABS: SEn = {0: .5f}, SEa = {1: .5f}'\
	.format(SEnABS,SEaABS))
	print('# - Josephson current: band: {0: .5f}, gap: {1: .5f}, total: {2: .5f}'\
	.format(JC_A[0],JC_A[1],JC))
	print('# U     Delta   GammaR  GammaL  eps     Phi/pi  wABS'+' '*12+'n'+' '*15+'mu'\
	+' '*14+'ResGn1'+' '*10+'ResGn2'+' '*10+'ResGa1'+' '*10+'JC')
print('{0: .3f}\t{1: .3f}\t{2: .3f}\t{3: .3f}\t{4: .3f}\t{5: .3f}\t{6: .5f}\
\t{7: .5f}\t{8: .5f}\t{9: .5f}\t{10: .5f}\t{11: .5f}\t{12: .5f}'\
.format(U,Delta,GammaR,GammaL,eps,P,wzeroInt,n,mu,Res_A[0],Res_A[1],Res_A[2],JC))
#print('{0: .3f}\t{1: .5f}\t{2: .5f}\t{3: .5f}'.format(P,JC_A[0],JC_A[1],JC))
if chat: print('# '+argv[0]+' DONE after {0: .2f} seconds.'.format(time()-t))

## secondPT.py end ##

