## SQUAD - superconducting quantum dot
## self-consistent second order perturbation theory solver
## uses scipy, optimized on Python 2.7.5
## Vladislav Pokorny; 2015-2018; pokornyv@fzu.cz

from __future__ import print_function
import scipy as sp
from scipy.optimize import brentq, fixed_point
from sys import argv, exit, version_info
from time import ctime
from squadlib1 import FillEnergies, AndreevEnergy, GFresidues, SolveHF, FillGreenHF,KondoTemperature
from squadlib2 import *
import params as p

U      = float(argv[1])
Delta  = float(argv[2])
GammaR = float(argv[3])
GammaL = float(argv[4])*GammaR
eps    = float(argv[5])
P      = float(argv[6])
GammaN = 0.0 	      ## for compatibility with functions from ssn branch (incl. normal electrode)

ed     = eps-U/2.0      ## localized energy level shifted to symmetry point
Phi    = P*sp.pi        ## phase difference

params_F = [U,Delta,GammaR,GammaL,GammaN,Phi,eps,0.0]

FitMin = 20.0
FitMax = 30.0

## In case you run into RuntimeWarning: invalid value encountered in power:
## for Kramers-Kronig we need range(N)**3 array, for large N it can 
## hit the limit of 2**63 = 9223372036854775808 of signed int
## large values of N also introduce instability to calcualtion of ABS
N  = 2**p.P['M']-1            ## number of points for bubble/self-energy FFT calculation
dE = p.P['dE']
dE_dec = int(-sp.log10(p.P['dE']))
En_F   = FillEnergies(p.P['dE'],N)

SEtype  = 'sc2nd'		## identifier for output files, other methods are not implemented
chat = p.P['WriteIO']   ## do we write calculation details to the standard output?


## printing header ########################################
ver = str(version_info[0])+'.'+str(version_info[1])+'.'+str(version_info[2])
if chat: print('#'*100)
if chat: print('# generated by '+str(argv[0])+', python version: '+str(ver)+\
', SciPy version: '+str(sp.version.version)+',   '+str(ctime()))
if chat: print('# U ={0: .3f}, Delta ={1: .3f}, GammaR ={2: .3f}, \
GammaL ={3: .3f}, eps ={4: .3f}, Phi/pi ={5: .3f}'.format(U,Delta,GammaR,GammaL,eps,P))
if chat: print('# Kondo temperature (from Bethe a.): {0: .5f}'.format(float(KondoTemperature(U,GammaR+GammaL,eps))))
if chat: print('# energy axis: [{0: .5f} ..{1: .5f}], step ={2: .5f}, length ={3: 3d}'\
.format(En_F[0],En_F[-1],p.P['dE'],len(En_F)))

## calculating the Hartree-Fock parameters ################
if chat: print('#\n# calculating HF solution')
try:
	[n,mu,wzero,ErrMsgHF] = SolveHF(params_F)
except RuntimeError:
	print('#  Error: failed to calculate HF solution.')
	exit(0)

hfe = ed+U*n				## Hartree-Fock energy level
wzero = AndreevEnergy(U,GammaR,GammaL,Delta,Phi,hfe,mu,p.P['ABSinit_val'])		## HF ABS frequencies

[GFn_F,GFa_F,EdgePos1,EdgePos2,ABSposGF1,ABSposGF2] = FillGreenHF(U,Delta,GammaR,GammaL,hfe,Phi,mu,wzero,En_F)
if p.P['Write_HFGF']: 
	WriteFile(En_F,GFn_F,GFa_F,params_F,wzero,'HF_green',p.P['EmaxFiles'],p.P['EstepFiles'])
[ResGnp1,ResGnh1,ResGa1] = GFresidues(U,Delta,GammaR,GammaL,hfe,Phi,mu,-wzero) ## HF residues at -w0
[ResGnp2,ResGnh2,ResGa2] = GFresidues(U,Delta,GammaR,GammaL,hfe,Phi,mu, wzero) ## HF residues at +w0
ResOld_F = sp.array([ResGnp1,ResGnp2,ResGa1])
IDin = IntDOS(GFn_F,En_F)

if chat: print('# - Hartree-Fock solution: n ={0: .5f}, mu ={1: .5f}, wABS ={2: .5f}, int(DoS) ={3: .5f}'\
.format(float(n),float(mu),float(wzero),float(IDin)))
if chat: print('# - HF residues: Gn: [{0: .5f}, {1: .5f}], Ga: [{2: .5f}, {2: .5f}]'\
.format(float(ResGnp1),float(ResGnp2),float(ResGa1)))

if chat: print('#\n# calculating second-order PT solution')

## bubbles and vertex ######################################
## two-particle bubble from HF
[Chin_F,Chia_F,ABSposChi1,ABSposChi2] = TwoParticleBubbles(GFn_F,GFa_F,En_F,wzero) 
if p.P['Write_Bubble']: 
	WriteFile(En_F,Chin_F,Chia_F,params_F,En_F[ABSposChi1],'HF_bubbles',p.P['EmaxFiles'],p.P['EstepFiles'])
## second-order kernel of the Schwinger-Dyson equation (without the static HF parts U*n & U*mu)
## other kernels are not implemented, feel free to do it
if SEtype == 'sc2nd': ChiGamma_F = U**2*(Chin_F+Chia_F)

## dynamical self-energy ###################################
## solution of the Schwinger-Dyson equation
[Sigman_F,Sigmaa_F] = SelfEnergy(GFn_F,GFa_F,ChiGamma_F,En_F)
if p.P['Write_2ndSE']: 
	WriteFile(En_F,Sigman_F,Sigmaa_F,params_F,0.0,'2nd_SE',p.P['EmaxFiles'],p.P['EstepFiles'])

## initial guess for the static part of self-energy ############
n  = ElectronDensity(params_F,n,mu,Sigman_F,Sigmaa_F,En_F)
mu = CooperPairDensity(params_F,n,mu,Sigman_F,Sigmaa_F,En_F)

## static self-energy ######################################
## the dynamic part is not changed anymore, charge consistency is aquired via shift in the static part
if chat: print('# - iterating densities')
n_old = 1e5
mu_old = 1e5
while any([sp.fabs(n-n_old)>p.P['ConvN'],sp.fabs(mu-mu_old)>p.P['ConvN']]):
	n_old = n
	mu_old = mu
	if p.P['rootf'] == 'brentq':
		if eps == 0.0: n = 0.5 ## half-filling
		else: 
			eqnN = lambda x: x - ElectronDensity(params_F,x,mu,Sigman_F,Sigmaa_F,En_F)
			n = brentq(eqnN,0.0,1.0,xtol = p.P['ConvX'])
		eqnA = lambda x: x - CooperPairDensity(params_F,n,x,Sigman_F,Sigmaa_F,En_F)
		mu = brentq(eqnA,p.P['MuMin'],p.P['MuMax'],xtol = p.P['ConvX'])	# change upper and lower limits if needed
	elif p.P['rootf'] == 'fixed_point':
		if eps == 0.0: n = 0.5 ## half-filling
		else: 			
			eqnN = lambda x: ElectronDensity(params_F,x,mu,Sigman_F,Sigmaa_F,En_F)
			n = fixed_point(eqnN,n_old,xtol = p.P['ConvX'])
		eqnA = lambda x: CooperPairDensity(params_F,n,x,Sigman_F,Sigmaa_F,En_F)
		mu = fixed_point(eqnA,mu_old,xtol = p.P['ConvX'])
		if chat: print('# - - n ={0: .5f}, mu ={1: .5f}'.format(float(n),float(mu)))
	if chat: print('# - - n ={0: .5f}, mu ={1: .5f}'.format(float(n),float(mu)))
	hfe = ed + U*n ## update the HF energy

## interacting Green's function ############################
[GFn_F,GFa_F,Det_F,ABS_F,ABSpos_F,Res_F] = FillGreensFunction(params_F,n,mu,Sigman_F,Sigmaa_F,En_F)
wzeroInt = ABS_F[1] ## ABS energy of the interacting system
ABSposInt1 = ABSpos_F[0]
if p.P['Write_2ndGF']: 
	WriteFile(En_F,GFn_F,GFa_F,params_F,wzeroInt,'2nd_green',p.P['EmaxFiles'],p.P['EstepFiles'])

## final checks and writing the results ####################
n_final  = ElectronDensity(params_F,n,mu,Sigman_F,Sigmaa_F,En_F)
mu_final = CooperPairDensity(params_F,n,mu,Sigman_F,Sigmaa_F,En_F)
if chat: print('# - final densities: n ={0: .5f}, mu ={1: .5f}'.format(float(n_final),float(mu_final)))
IDout = IntDOS(GFn_F,En_F)
if chat: print('# - output from 2nd order: wABS = {0: .5f}, int(DoS) = {1: .5f}'\
.format(float(sp.fabs(wzeroInt)),float(IDout)))
if chat: print('# - 2ndPT residues: Gn: [{0: .5f}, {1: .5f}], Ga: [{2: .5f}, {2: .5f}]'\
.format(float(Res_F[0]),float(Res_F[1]),float(Res_F[2])))
if sp.sign(Res_F[2]*ResOld_F[2]) < 0.0 and chat:
	print('# Warning: Residue of anomalous function changes sign, {0: .5f} -> {1: .5f} (false pi-phase?)'\
	.format(float(ResOld_F[2]),float(Res_F[2])))
if sp.fabs(Res_F[0]-Res_F[1]) > 1e-3 and eps == 0.0 and chat:
	print("# Warning: Residues of normal GF at ABS don't match.")
SEnABS = sp.real(Sigman_F[ABSpos_F[0]])
SEaABS = sp.real(Sigmaa_F[ABSpos_F[0]])
if chat: print('# - self-energies at ABS: SEn = {0: .5f}, SEa = {1: .5f}'.format(float(SEnABS),float(SEaABS)))
JC_F = JosephsonCurrent(params_F,GFa_F,En_F,Res_F[2],wzeroInt)
print('# - Josephson current: band: {0: .5f}, gap: {1: .5f}, total: {2: .5f}'.format(float(JC_F[0]),float(JC_F[1]),float(JC_F[0]+JC_F[1])))

print('# U     GammaR  GammaL  eps     Phi/pi  wABS'+' '*12+'n'+' '*15+'mu'+' '*14+'ResGn1'+' '*10+'ResGn2'+' '*10+'ResGa1')
print('{0: .3f}\t{1: .3f}\t{2: .3f}\t{3: .3f}\t{4: .3f}\t{5: .5f}\t{6: .5f}\t{7: .5f}\t{8: .5f}\t{9: .5f}\t{10: .5f}'\
.format(U,GammaR,GammaL,eps,P,float(wzeroInt),float(n),float(mu),Res_F[0],Res_F[1],Res_F[2]))

## secondPT.py end ##
