# coding: utf-8
import warnings
import time
import logging
import json
from random import random
from scipy.interpolate import griddata
from scipy.constants.codata import value as _cd
from pprint import pprint
import os

import numpy as np
from math import log

from pymatgen.io.vasp import Vasprun, Spin, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from math import pi
from monty.json import MontyEncoder
import cProfile
from copy import deepcopy
import multiprocessing
from joblib import Parallel, delayed
from analytical_band_from_BZT import Analytical_bands, outer, get_dos_from_poly_bands, get_energy, get_poly_energy


__author__ = "Alireza Faghaninia, Jason Frost, Anubhav Jain"
__copyright__ = "Copyright 2017, HackingMaterials"
__version__ = "0.1"
__maintainer__ = "Alireza Faghaninia"
__email__ = "alireza.faghaninia@gmail.com"
__status__ = "Development"
__date__ = "July 2017"


# some global constants
hbar = _cd('Planck constant in eV s') / (2 * pi)
m_e = _cd('electron mass')  # in kg
Ry_to_eV = 13.605698066
A_to_m = 1e-10
m_to_cm = 100.00
A_to_nm = 0.1
e = _cd('elementary charge')
k_B = _cd("Boltzmann constant in eV/K")
epsilon_0 = 8.854187817e-12  # Absolute value of dielectric constant in vacuum [C**2/m**2N]
default_small_E = 1  # eV/cm the value of this parameter does not matter
dTdz = 10.0  # K/cm
sq3 = 3 ** 0.5


def norm(v):
    """method to quickly calculate the norm of a vector (v: 1x3 or 3x1) as numpy.linalg.norm is slower for this case"""
    return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5


def grid_norm(grid):
    return (grid[:,:,:,0]**2 + grid[:,:,:,1]**2 + grid[:,:,:,2]**2) ** 0.5


def f0(E, fermi, T):
    """returns the value of Fermi-Dirac at equilibrium for E (energy), fermi [level] and T (temperature)"""
    if E - fermi > 5:
        return 0.0
    elif E - fermi < -5:
        return 1.0
    else:
        return 1 / (1 + np.exp((E - fermi) / (k_B * T)))



def df0dE(E, fermi, T):
    """returns the energy derivative of the Fermi-Dirac equilibrium distribution"""
    if E - fermi > 5 or E - fermi < -5:  # This is necessary so at too low numbers python doesn't return NaN
        return 0.0
    else:
        return -1 / (k_B * T) * np.exp((E - fermi) / (k_B * T)) / (1 + np.exp((E - fermi) / (k_B * T))) ** 2



def cos_angle(v1, v2):
    """
    returns cosine of the angle between two 3x1 or 1x3 vectors
    """
    norm_v1, norm_v2 = norm(v1), norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 1.0  # In case of the two points are the origin, we assume 0 degree; i.e. no scattering: 1-X==0
    else:
        return np.dot(v1, v2) / (norm_v1 * norm_v2)



def fermi_integral(order, fermi, T, initial_energy=0, wordy=False):
    """
    returns the Fermi integral (e.g. for calculating single parabolic band acoustic phonon mobility
    Args:
        order (int): the order of integral
        fermi (float): the actual Fermi level of the band structure (not relative to CBM/VBM):
        T (float): the temperature
        initial_energy (float): the actual CBM/VBM energy in eV
        wordy (bool): whether to print out the integrals or not
    """
    fermi = fermi - initial_energy
    integral = 0.
    nsteps = 100000.0
    # TODO: 1000000 works better (converges!) but for faster testing purposes we use larger steps
    # emesh = np.linspace(0.0, 30*k_B*T, nsteps) # We choose 20kBT instead of infinity as the fermi distribution will be 0
    emesh = np.linspace(0.0, 30 * k_B * T,
                        nsteps)  # We choose 20kBT instead of infinity as the fermi distribution will be 0
    dE = (emesh[-1] - emesh[0]) / (nsteps - 1.0)
    for E in emesh:
        integral += dE * (E / (k_B * T)) ** order / (1. + np.exp((E - fermi) / (k_B * T)))

    if wordy:
        print "order {} fermi integral at fermi={} and {} K".format(order, fermi, T)
        print integral
    return integral



def GB(x, eta):
    """Gaussian broadening. At very small eta values (e.g. 0.005 eV) this function goes to the dirac-delta of x.
    Args:
        x (float): the mean value of the nomral distribution
        eta (float): the standard deviation of the normal distribution
        """

    return 1 / np.pi * 1 / eta * np.exp(-(x / eta) ** 2)

    ## although both expressions conserve the final transport properties, the one below doesn't conserve the scat. rates
    # return np.exp(-(x/eta)**2)



def calculate_Sio_list(tp, c, T, ib, once_called, kgrid, cbm_vbm, epsilon_s, epsilon_inf):
    S_i_list = [0.0 for ik in kgrid[tp]["kpoints"][ib]]
    S_i_th_list = [0.0 for ik in kgrid[tp]["kpoints"][ib]]
    S_o_list = [0.0 for ik in kgrid[tp]["kpoints"][ib]]
    S_o_th_list = [0.0 for ik in kgrid[tp]["kpoints"][ib]]

    for ik in range(len(kgrid[tp]["kpoints"][ib])):
        S_i_list[ik], S_i_th_list[ik], S_o_list[ik], S_o_th_list[ik] = \
            calculate_Sio(tp, c, T, ib, ik, once_called, kgrid, cbm_vbm, epsilon_s, epsilon_inf)

    return [S_i_list, S_i_th_list, S_o_list, S_o_th_list]



def calculate_Sio(tp, c, T, ib, ik, once_called, kgrid, cbm_vbm, epsilon_s, epsilon_inf):
    """calculates and returns the in and out polar optical phonon inelastic scattering rates. This function
        is defined outside of the AMSET class to enable parallelization.
    Args:
        tp (str): the type of the bands; "n" for the conduction and "p" for the valence bands
        c (float): the carrier concentration
        T (float): the temperature
        ib (int): the band index
        ik (int): the k-point index
        once_called (bool): whether this function was once called hence S_o and S_o_th calculated once or not
        kgrid (dict): the main kgrid variable in AMSET (AMSET.kgrid)
        cbm_vbm (dict): the dict containing information regarding the cbm and vbm (from AMSET.cbm_vbm)
        epsilon_s (float): static dielectric constant
        epsilon_inf (float): high-frequency dielectric constant
        """
    S_i = [np.array([1e-32, 1e-32, 1e-32]), np.array([1e-32, 1e-32, 1e-32])]
    S_i_th = [np.array([1e-32, 1e-32, 1e-32]), np.array([1e-32, 1e-32, 1e-32])]
    S_o = [np.array([1e-32, 1e-32, 1e-32]), np.array([1e-32, 1e-32, 1e-32])]
    S_o_th = [np.array([1e-32, 1e-32, 1e-32]), np.array([1e-32, 1e-32, 1e-32])]
    # S_o = np.array([self.gs, self.gs, self.gs])

    v = kgrid[tp]["norm(v)"][ib][ik] / sq3  # 3**0.5 is to treat each direction as 1D BS
    k = kgrid[tp]["norm(k)"][ib][ik]
    a = kgrid[tp]["a"][ib][ik]
    c_ = kgrid[tp]["c"][ib][ik]
    f = kgrid[tp]["f"][c][T][ib][ik]
    f_th = kgrid[tp]["f_th"][c][T][ib][ik]
    N_POP = kgrid[tp]["N_POP"][c][T][ib][ik]

    for j, X_Epm in enumerate(["X_Eplus_ik", "X_Eminus_ik"]):
        # bypass k-points that cannot have k_plus or k_minus associated with them
        if tp == "n" and X_Epm == "X_Eminus_ik" and kgrid[tp]["energy"][ib][ik] - hbar * \
                kgrid[tp]["W_POP"][ib][ik] < cbm_vbm[tp]["energy"]:
            continue

        if tp == "p" and X_Epm == "X_Eplus_ik" and kgrid[tp]["energy"][ib][ik] + hbar * \
                kgrid[tp]["W_POP"][ib][ik] > cbm_vbm[tp]["energy"]:
            continue

        # TODO: see how does dividing by counted affects results, set to 1 to test: #20170614: in GaAs,
        # they are all equal anyway (at least among the ones checked)
        # ACTUALLY this is not true!! for each ik I get different S_i values at different k_prm

        counted = len(kgrid[tp][X_Epm][ib][ik])
        for X_ib_ik in kgrid[tp][X_Epm][ib][ik]:
            X, ib_pm, ik_pm = X_ib_ik
            g_pm = kgrid[tp]["g"][c][T][ib_pm][ik_pm]
            g_pm_th = kgrid[tp]["g_th"][c][T][ib_pm][ik_pm]
            v_pm = kgrid[tp]["norm(v)"][ib_pm][ik_pm] / sq3  # 3**0.5 is to treat each direction as 1D BS
            k_pm = kgrid[tp]["norm(k)"][ib_pm][ik_pm]
            abs_kdiff = abs(k_pm - k)
            if abs_kdiff < 1e-4:
                counted -= 1
                continue
            a_pm = kgrid[tp]["a"][ib_pm][ik_pm]
            c_pm = kgrid[tp]["c"][ib_pm][ik_pm]

            if tp == "n":
                f_pm = kgrid[tp]["f"][c][T][ib_pm][ik_pm]
                f_pm_th = kgrid[tp]["f_th"][c][T][ib_pm][ik_pm]
            else:
                f_pm = 1 - kgrid[tp]["f"][c][T][ib_pm][ik_pm]
                f_pm_th = 1 - kgrid[tp]["f_th"][c][T][ib_pm][ik_pm]


            A_pm = a * a_pm + c_ * c_pm * (k_pm ** 2 + k ** 2) / (2 * k_pm * k)
            beta_pm = (e ** 2 * kgrid[tp]["W_POP"][ib_pm][ik_pm]) / (4 * pi * hbar * v_pm) * \
                      (1 / (epsilon_inf * epsilon_0) - 1 / (epsilon_s * epsilon_0)) * 6.2415093e20

            if not once_called:
                lamb_opm = beta_pm * (
                    A_pm ** 2 * log((k_pm + k) / (abs_kdiff + 1e-4)) - A_pm * c_ * c_pm - a * a_pm * c_ * c_pm)
                # because in the scalar form k+ or k- is suppused to be unique, here we take average
                S_o[j] += (N_POP + j + (-1) ** j * f_pm) * lamb_opm
                S_o_th[j] += (N_POP + j + (-1) ** j * f_pm_th) * lamb_opm

            lamb_ipm = beta_pm * (
                (k_pm ** 2 + k ** 2) / (2 * k * k_pm) * \
                A_pm ** 2 * log((k_pm + k) / (abs_kdiff + 1e-4)) - A_pm ** 2 - c_ ** 2 * c_pm ** 2 / 3)
            S_i[j] += (N_POP + (1 - j) + (-1) ** (1 - j) * f) * lamb_ipm * g_pm
            S_i_th[j] += (N_POP + (1 - j) + (-1) ** (1 - j) * f_th) * lamb_ipm * g_pm_th

        if counted > 0:
            S_i[j] /= counted
            S_i_th[j] /= counted
            S_o[j] /= counted
            S_o_th[j] /= counted

    return [sum(S_i), sum(S_i_th), sum(S_o), sum(S_o_th)]



class AMSET(object):
    """ This class is used to run AMSET on a pymatgen from a VASP run (i.e. vasprun.xml). AMSET is an ab initio model
    for calculating the mobility and Seebeck coefficient using Bolƒtzmann transport equation (BTE). The band structure
    in the Brilluin zone (BZ) is extracted from vasprun.xml to calculate the group velocity and transport properties
    in presence of various scattering mechanisms.

     Currently the following scattering mechanisms with their corresponding three-letter abbreviations implemented are:
     ionized impurity scattering (IMP), acoustic phonon deformation potential (ACD), piezoelectric (PIE), and charged
     dislocation scattering (DIS). Also, longitudinal polar optical phonon (POP) in implemented as an inelastic
     scattering mechanism that can alter the electronic distribution (the reason BTE has to be solved explicitly; for
     more information, see references [R, A]).

     you can control the level of theory via various inputs. For example, by assuming that the band structure is
     isotropic at the surrounding point of each k-point (i.e. bs_is_isotropic == True), once can significantly reduce
     the computational effort needed for accurate numerical integration of the scatterings.

    * a small comment on the structure of this code: the calculations are done and stred in two main dictionary type
    variable called kgrid and egrid. kgrid contains all calculations that are done in k-space meaning that for each
    k-point and each band that is included there is a number/vector/property stored. On the other hand, the egrid
    is everything in energy scale hence we have number/vector/property stored at each energy point.

     References:
         [R]: D. L. Rode, Low-Field Electron Transport, Elsevier, 1975, vol. 10., DOI: 10.1016/S0080-8784(08)60331-2
         [A]: A. Faghaninia, C. S. Lo and J. W. Ager, Phys. Rev. B, "Ab initio electronic transport model with explicit
          solution to the linearized Boltzmann transport equation" 2015, 91(23), 5100., DOI: 10.1103/PhysRevB.91.235123
         [Q]: B. K. Ridley, Quantum Processes in Semiconductors, oxford university press, Oxford, 5th edn., 2013.
          DOI: 10.1093/acprof:oso/9780199677214.001.0001

     """
    def __init__(self, calc_dir, material_params, model_params={}, performance_params={},
                 dopings=None, temperatures=None, k_integration=True, e_integration=False, fermi_type='k'):
        """
        Args:
            calc_dir (str): path to the vasprun.xml (a required argument)
            material_params (dict): parameters related to the material (a required argument)
            model_params (dict): parameters related to the model used and the level of theory
            performance_params (dict): parameters related to convergence, speed, etc.
            dopings ([float]): list of input carrier concentrations; c<0 for electrons and c>0 for holes
            temperatures ([float]): list of input temperatures
        """

        self.calc_dir = calc_dir
        self.dopings = dopings or [-1e16, -1e17, -1e18, -1e19, -1e20, -1e21, 1e16, 1e17, 1e18, 1e19, 1e20, 1e21]
        self.all_types = list(set([self.get_tp(c) for c in self.dopings]))
        self.tp_title = {"n": "conduction band(s)", "p": "valence band(s)"}
        self.temperatures = temperatures or map(float, [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000])
        self.debug_tp = self.get_tp(self.dopings[0])
        logging.debug("""debug_tp: "{}" """.format(self.debug_tp))
        self.set_material_params(material_params)
        self.set_model_params(model_params)
        self.set_performance_params(performance_params)
        self.k_integration = k_integration
        self.e_integration = e_integration
        self.fermi_calc_type = fermi_type

        self.read_vrun(calc_dir=self.calc_dir, filename="vasprun.xml")
        if self.poly_bands:
            self.cbm_vbm["n"]["energy"] = self.dft_gap
            self.cbm_vbm["p"]["energy"] = 0.0
            # @albalu why are the conduction and valence band k points being set to the same value?
                # because the way poly band generates a band structure is by mirroring conduction and valence bands
            # @albalu what is the format of self.poly_bands? it's a nested list, this can be improved actually
            self.cbm_vbm["n"]["kpoint"] = self.cbm_vbm["p"]["kpoint"] = self.poly_bands[0][0][0]

        self.num_cores = max(int(multiprocessing.cpu_count()/4), 8)
        if self.parallel:
            logging.info("number of cpu used in parallel mode: {}".format(self.num_cores))



    def remove_from_grids(self, kgrid_rm_list, egrid_rm_list):
        """deletes dictionaries storing properties about k points and E points that are no longer
        needed from fgrid and egrid"""
        for tp in ["n", "p"]:
            for rm in kgrid_rm_list:
                try:
                    del (self.kgrid[tp][rm])
                except:
                    pass
            # for erm in ["all_en_flat", "f_th", "g_th", "S_i_th", "S_o_th"]:
            for erm in egrid_rm_list:
                try:
                    del (self.egrid[tp][erm])
                except:
                    pass



    def run(self, coeff_file, kgrid_tp="coarse"):
        """
        Function to run AMSET and generate the main outputs.

        Args:
        coeff_file: the fort.123* file which contains the coefficients of the interpolated band structure
                it is generated by a modified version of BoltzTraP
        kgrid_tp (str): define the density of k-point mesh; options: "coarse", "fine"
        """

        self.init_kgrid(coeff_file=coeff_file, kgrid_tp=kgrid_tp)
        logging.debug("self.cbm_vbm: {}".format(self.cbm_vbm))

        self.f0_array = {c: {T: {'n': None, 'p': None} for T in self.temperatures} for c in self.dopings}
        if self.fermi_calc_type == 'k':
            self.fermi_level = self.find_fermi_k()
            self.calc_doping = {c: {T: {'n': None, 'p': None} for T in self.temperatures} for c in self.dopings}
            for c in self.dopings:
                for T in self.temperatures:
                    for tp in ['n', 'p']:
                        self.f0_array[c][T][tp] = 1 / (np.exp((self.energy_array[tp] - self.fermi_level[c][T]) / (k_B * T)) + 1)
                    self.calc_doping[c][T]['n'] = -self.integrate_over_states(self.f0_array[c][T]['n'])
                    self.calc_doping[c][T]['p'] = self.integrate_over_states(1-self.f0_array[c][T]['p'])

        self.init_egrid(dos_tp="standard")

        print('fermi level = {}'.format(self.fermi_level))

        self.bandgap = min(self.egrid["n"]["all_en_flat"]) - max(self.egrid["p"]["all_en_flat"])
        if abs(self.bandgap - (self.cbm_vbm["n"]["energy"] - self.cbm_vbm["p"]["energy"] + self.scissor)) > k_B * 300:
            warnings.warn("The band gaps do NOT match! The selected k-mesh is probably too coarse.")
            # raise ValueError("The band gaps do NOT match! The selected k-mesh is probably too coarse.")

        # initialize g in the egrid
        self.map_to_egrid("g", c_and_T_idx=True, prop_type="vector")
        self.map_to_egrid(prop_name="velocity", c_and_T_idx=False, prop_type="vector")


        # logging.debug("average of the group velocity in egrid: \n {}".format(
        #     np.mean(self.egrid[self.debug_tp]["velocity"], 0)))

        # find the indexes of equal energy or those with ±hbar*W_POP for scattering via phonon emission and absorption
        if not self.bs_is_isotropic or "POP" in self.inelastic_scatterings:
            self.generate_angles_and_indexes_for_integration()

        # calculate all elastic scattering rates in kgrid and then map it to egrid:
        for sname in self.elastic_scatterings:
            self.s_elastic(sname=sname)
            self.map_to_egrid(prop_name=sname)

        self.map_to_egrid(prop_name="_all_elastic")
        self.map_to_egrid(prop_name="relaxation time")

        for c in self.dopings:
            for T in self.temperatures:
                #fermi = self.egrid["fermi"][c][T]
                fermi = self.fermi_level[c][T]
                for tp in ["n", "p"]:
                    fermi_norm = fermi - self.cbm_vbm[tp]["energy"]
                    for ib in range(len(self.kgrid[tp]["energy"])):
                        for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                            E = self.kgrid[tp]["energy"][ib][ik]
                            v = self.kgrid[tp]["velocity"][ib][ik]

                            self.kgrid[tp]["f0"][c][T][ib][ik] = f0(E, fermi, T) * 1.0
                            self.kgrid[tp]["df0dk"][c][T][ib][ik] = hbar * df0dE(E, fermi, T) * v  # in cm
                            self.kgrid[tp]["electric force"][c][T][ib][ik] = -1 * \
                                                                             self.kgrid[tp]["df0dk"][c][T][ib][
                                                                                 ik] * default_small_E / hbar  # in 1/s

                            E_norm = E - self.cbm_vbm[tp]["energy"]
                            # self.kgrid[tp]["electric force"][c][T][ib][ik] = 1
                            self.kgrid[tp]["thermal force"][c][T][ib][ik] = - v * f0(E_norm, fermi_norm, T) * (
                            1 - f0(E_norm, fermi_norm, T)) * ( \
                                                                                E_norm / (k_B * T) - self.egrid[
                                                                                    "Seebeck_integral_numerator"][c][T][
                                                                                    tp] /
                                                                                self.egrid[
                                                                                    "Seebeck_integral_denominator"][c][
                                                                                    T][tp]) * dTdz / T

                dop_tp = self.get_tp(c)
                f0_removed = self.array_from_kgrid('f0', dop_tp, c, T)
                f0_all = 1 / (np.exp((self.energy_array[dop_tp] - self.fermi_level[c][T]) / (k_B * T)) + 1)
                if c < 0:
                    result = self.integrate_over_states(f0_removed)
                    result2 = self.integrate_over_states(f0_all)
                    print('integral (points removed) of f0 over k at c={}, T={}: {}'.format(c, T, result))
                    print('integral (all points) of f0 over k at c={}, T={}: {}'.format(c, T, result2))
                if c > 0:
                    p_result = self.integrate_over_states(1-f0_removed)
                    p_result2 = self.integrate_over_states(1-f0_all)
                    print('integral (points removed) of 1-f0 over k at c={}, T={}: {}'.format(c, T, p_result))
                    print('integral (all points) of 1-f0 over k at c={}, T={}: {}'.format(c, T, p_result2))


        self.map_to_egrid(prop_name="f0", c_and_T_idx=True, prop_type="vector")
        self.map_to_egrid(prop_name="df0dk", c_and_T_idx=True, prop_type="vector")

        # solve BTE in presence of electric and thermal driving force to get perturbation to Fermi-Dirac: g
        self.solve_BTE_iteratively()

        # if "POP" in self.inelastic_scatterings:
        #     for key in ["plus", "minus"]:
        #         with open("X_E{}_ik".format(key), "w") as fp:
        #             json.dump(self.kgrid[self.debug_tp]["X_E{}_ik".format(key)][0], fp, cls=MontyEncoder)

        if self.k_integration:
            self.calculate_transport_properties_with_k()
        if self.e_integration:
            self.calculate_transport_properties_with_E()

        # logging.debug('self.kgrid_to_egrid_idx[self.debug_tp]: \n {}'.format(self.kgrid_to_egrid_idx[self.debug_tp]))
        # logging.debug('self.kgrid["velocity"][self.debug_tp][0]: \n {}'.format(self.kgrid[self.debug_tp]["velocity"][0]))
        # logging.debug('self.egrid["velocity"][self.debug_tp]: \n {}'.format(self.egrid[self.debug_tp]["velocity"]))

        # kremove_list = ["W_POP", "effective mass", "kweights", "a", "c""",
        #                 "f_th", "g_th", "S_i_th", "S_o_th"]

        kgrid_rm_list = ["effective mass", "kweights",
                         "f_th", "S_i_th", "S_o_th"]
        #egrid_rm_list = ["f_th", "S_i_th", "S_o_th"]
        egrid_rm_list = []
        self.remove_from_grids(kgrid_rm_list, egrid_rm_list)

        if self.k_integration:
            pprint(self.mobility)
        if self.e_integration:
            pprint(self.egrid["mobility"])
        #pprint(self.egrid["seebeck"])



    def write_input_files(self):
        """writes all 3 types of inputs in json files for example to
        conveniently track what inputs had been used later or read
        inputs from files (see from_files method)"""
        material_params = {
            "epsilon_s": self.epsilon_s,
            "epsilon_inf": self.epsilon_inf,
            "C_el": self.C_el,
            "W_POP": self.W_POP / (1e12 * 2 * pi),
            "P_PIE": self.P_PIE,
            "E_D": self.E_D,
            "N_dis": self.N_dis,
            "scissor": self.scissor,
            "donor_charge": self.charge["n"],
            "acceptor_charge": self.charge["p"],
            "dislocations_charge": self.charge["dislocations"]
        }

        model_params = {
            "bs_is_isotropic": self.bs_is_isotropic,
            "elastic_scatterings": self.elastic_scatterings,
            "inelastic_scatterings": self.inelastic_scatterings,
            "poly_bands": self.poly_bands
        }

        performance_params = {
            "nkibz": self.nkibz,
            "dE_min": self.dE_min,
            "Ecut": self.Ecut,
            "adaptive_mesh": self.adaptive_mesh,
            "dos_bwidth": self.dos_bwidth,
            "nkdos": self.nkdos,
            "wordy": self.wordy,
            "BTE_iters": self.BTE_iters
        }

        with open("material_params.json", "w") as fp:
            json.dump(material_params, fp, sort_keys=True, indent=4, ensure_ascii=False, cls=MontyEncoder)
        with open("model_params.json", "w") as fp:
            json.dump(model_params, fp, sort_keys=True, indent=4, ensure_ascii=False, cls=MontyEncoder)
        with open("performance_params.json", "w") as fp:
            json.dump(performance_params, fp, sort_keys=True, indent=4, ensure_ascii=False, cls=MontyEncoder)



    def set_material_params(self, params):

        self.epsilon_s = params["epsilon_s"]
        self.epsilon_inf = params["epsilon_inf"]
        self.C_el = params["C_el"]
        self.W_POP = params["W_POP"] * 1e12 * 2 * pi

        self.P_PIE = params.get("P_PIE", 0.15)  # unitless
        self.E_D = params.get("E_D", {"n": 4.0, "p": 4.0})

        self.N_dis = params.get("N_dis", 0.1)  # in 1/cm**2
        self.scissor = params.get("scissor", 0.0)

        donor_charge = params.get("donor_charge", 1.0)
        acceptor_charge = params.get("acceptor_charge", 1.0)
        dislocations_charge = params.get("dislocations_charge", 1.0)
        self.charge = {"n": donor_charge, "p": acceptor_charge, "dislocations": dislocations_charge}



    def set_model_params(self, params):
        """function to set instant variables related to the model and the level of the theory;
        these are set based on params (dict) set by the user or their default values"""

        self.bs_is_isotropic = params.get("bs_is_isotropic", False)
        # TODO: remove this if later when anisotropic band structure is supported
        # if not self.bs_is_isotropic:
        #     raise IOError("Anisotropic option or bs_is_isotropic==False is NOT supported yet, please check back later")
        # what scattering mechanisms to be included
        self.elastic_scatterings = params.get("elastic_scatterings", ["ACD", "IMP", "PIE"])
        self.inelastic_scatterings = params.get("inelastic_scatterings", ["POP"])

        self.poly_bands = params.get("poly_bands", None)

        # TODO: self.gaussian_broadening is designed only for development version and must be False, remove it later.
        # because if self.gaussian_broadening the mapping to egrid will be done with the help of Gaussian broadening
        # and that changes the actual values
        self.gaussian_broadening = False
        self.soc = params.get("soc", False)
        logging.info("bs_is_isotropic: {}".format(self.bs_is_isotropic))



    def set_performance_params(self, params):
        self.nkibz = params.get("nkibz", 40)
        self.dE_min = params.get("dE_min", 0.0001)
        self.nE_min = params.get("nE_min", 2)
        # max eV range after which occupation is zero, we set this at least to 10*kB*300
        c_factor = max(1, 2*abs(max([log(abs(ci)/float(1e19)) for ci in self.dopings]))**0.15)
        Ecut = params.get("Ecut", c_factor * 15 * k_B * max(self.temperatures + [300]))
        # Ecut = params.get("Ecut", 10 * k_B * max(self.temperatures + [300]))
        self.Ecut = {tp: Ecut if tp in self.all_types else Ecut/2.0 for tp in ["n", "p"]}
        for tp in ["n", "p"]:
            logging.debug("{}-Ecut: {} eV \n".format(tp, self.Ecut[tp]))
        self.adaptive_mesh = params.get("adaptive_mesh", False)

        self.dos_bwidth = params.get("dos_bwidth",
                                     0.05)  # in eV the bandwidth used for calculation of the total DOS (over all bands & IBZ k-points)
        self.nkdos = params.get("nkdos", 35)
        self.v_min = 100
        self.gs = 1e-32  # a global small value (generally used for an initial non-zero value)
        self.gl = 1e32  # a global large value

        # TODO: some of the current global constants should be omitted, taken as functions inputs or changed!
        self.wordy = params.get("wordy", False)
        self.BTE_iters = params.get("BTE_iters", 5)
        self.parallel = params.get("parallel", True)
        logging.info("parallel: {}".format(self.parallel))



    def __getitem__(self, key):
        if key == "kgrid":
            return self.kgrid
        elif key == "egrid":
            return self.egrid
        else:
            raise KeyError



    def get_dft_orbitals(self, bidx):
        projected = self._vrun.projected_eigenvalues
        # print len(projected[Spin.up][0][10])  # indexes : Spin, kidx, bidx, atomidx, s,py,pz,px,dxy,dyz,dz2,dxz,dx2

        s_orbital = [0.0 for k in self.DFT_cartesian_kpts]
        p_orbital = [0.0 for k in self.DFT_cartesian_kpts]
        for ik in range(len(self.DFT_cartesian_kpts)):
            s_orbital[ik] = sum(projected[Spin.up][ik][bidx])[0]
            if self.lorbit == 10:
                p_orbital[ik] = sum(projected[Spin.up][ik][bidx])[1]
            elif self.lorbit == 11:
                p_orbital[ik] = sum(sum(projected[Spin.up][ik][bidx])[1:4])
        return s_orbital, p_orbital



    def read_vrun(self, calc_dir=".", filename="vasprun.xml"):
        self._vrun = Vasprun(os.path.join(calc_dir, filename), parse_projected_eigen=True)
        self.volume = self._vrun.final_structure.volume
        logging.info("unitcell volume = {} A**3".format(self.volume))
        self.density = self._vrun.final_structure.density
        # @albalu why is this not called the reciprocal lattice? your _rec_lattice is better
        # self._lattice_matrix = self._vrun.lattice_rec.matrix / (2 * pi)
        # @albalu is there a convention to name variables that are other objects with a "_" in the front?
            # yes, these are the ones that users are absolutely not supposed to change
        self._rec_lattice = self._vrun.final_structure.lattice.reciprocal_lattice

        bs = self._vrun.get_band_structure()
        self.nbands = bs.nb_bands
        self.lorbit = 11 if len(sum(self._vrun.projected_eigenvalues[Spin.up][0][10])) > 5 else 10

        self.DFT_cartesian_kpts = np.array(
                [self._rec_lattice.get_cartesian_coords(k) for k in self._vrun.actual_kpoints])/ A_to_nm


        # Remember that python band index starts from 0 so bidx==9 refers to the 10th band in VASP
        cbm_vbm = {"n": {"kpoint": [], "energy": 0.0, "bidx": 0, "included": 0, "eff_mass_xx": [0.0, 0.0, 0.0]},
                   "p": {"kpoint": [], "energy": 0.0, "bidx": 0, "included": 0, "eff_mass_xx": [0.0, 0.0, 0.0]}}
        cbm = bs.get_cbm()
        vbm = bs.get_vbm()

        logging.info("total number of bands: {}".format(self._vrun.get_band_structure().nb_bands))
        # print bs.nb_bands

        cbm_vbm["n"]["energy"] = cbm["energy"]
        cbm_vbm["n"]["bidx"] = cbm["band_index"][Spin.up][0]
        cbm_vbm["n"]["kpoint"] = bs.kpoints[cbm["kpoint_index"][0]].frac_coords

        cbm_vbm["p"]["energy"] = vbm["energy"]
        cbm_vbm["p"]["bidx"] = vbm["band_index"][Spin.up][-1]
        cbm_vbm["p"]["kpoint"] = bs.kpoints[vbm["kpoint_index"][0]].frac_coords

        self.dft_gap = cbm["energy"] - vbm["energy"]
        logging.debug("DFT gap from vasprun.xml : {} eV".format(self.dft_gap))

        if self.soc:
            self.nelec = cbm_vbm["p"]["bidx"] + 1
            # self.dos_normalization_factor = self._vrun.get_band_structure().nb_bands
        else:
            self.nelec = (cbm_vbm["p"]["bidx"] + 1) * 2
            # self.dos_normalization_factor = self._vrun.get_band_structure().nb_bands*2

        logging.debug("total number of electrons nelec: {}".format(self.nelec))

        bs = bs.as_dict()
        if bs["is_spin_polarized"]:
            self.dos_emin = min(bs["bands"]["1"][0], bs["bands"]["-1"][0])
            self.dos_emax = max(bs["bands"]["1"][-1], bs["bands"]["-1"][-1])
        else:
            self.dos_emin = min(bs["bands"]["1"][0])
            self.dos_emax = max(bs["bands"]["1"][-1])

        if not self.poly_bands:
            for i, tp in enumerate(["n", "p"]):
                # Ecut = self.Ecut if tp in self.all_types else min(self.Ecut/10.0, 10*k_B*300/3.0)
                Ecut = self.Ecut[tp]
                sgn = (-1) ** i
                # @albalu what is this next line doing (even though it doesn't appear to be in use)?
                    # this part determines how many bands are have energy values close enough to CBM/VBM to be included
                while abs(min(sgn * bs["bands"]["1"][cbm_vbm[tp]["bidx"] + sgn * cbm_vbm[tp]["included"]]) -
                                          sgn * cbm_vbm[tp]["energy"]) < Ecut:
                    cbm_vbm[tp]["included"] += 1

                # TODO: for now, I only include 1 band for quicker testing
                #cbm_vbm[tp]["included"] = 1
        else:
            cbm_vbm["n"]["included"] = cbm_vbm["p"]["included"] = len(self.poly_bands)

        # TODO: change this later if the band indecies are corrected in Analytical_band class
        cbm_vbm["p"]["bidx"] += 1
        cbm_vbm["n"]["bidx"] = cbm_vbm["p"]["bidx"] + 1

        self.cbm_vbm = cbm_vbm
        logging.info("original cbm_vbm:\n {}".format(self.cbm_vbm))



    def get_tp(self, c):
        """returns "n" for n-tp or negative carrier concentration or "p" (p-tp)."""
        if c < 0:
            return "n"
        elif c > 0:
            return "p"
        else:
            raise ValueError("The carrier concentration cannot be zero! AMSET stops now!")

    def seeb_int_num(self, c, T):
        """wrapper function to do an integration taking only the concentration, c, and the temperature, T, as inputs"""
        fn = lambda E, fermi, T: f0(E, fermi, T) * (1 - f0(E, fermi, T)) * E / (k_B * T)
        # return {
        # t: self.integrate_over_DOSxE_dE(func=fn, tp=t, fermi=self.egrid["fermi"][c][T], T=T, normalize_energy=True) for
        # t in ["n", "p"]}
        return {
            t: self.integrate_over_DOSxE_dE(func=fn, tp=t, fermi=self.fermi_level[c][T], T=T, normalize_energy=True)
        for
            t in ["n", "p"]}

    def seeb_int_denom(self, c, T):
        """wrapper function to do an integration taking only the concentration, c, and the temperature, T, as inputs"""
        # fn = lambda E, fermi, T: f0(E, fermi, T) * (1 - f0(E, fermi, T))
        # return {t:self.integrate_over_DOSxE_dE(func=fn,tp=t,fermi=self.egrid["fermi"][c][T],T=T, normalize_energy=True) for t in ["n", "p"]}

        return {t: self.gs + self.integrate_over_E(prop_list=["f0x1-f0"], tp=t, c=c, T=T, xDOS=True) for t in
                ["n", "p"]}



    def calculate_property(self, prop_name, prop_func, for_all_E=False):
        """
        calculate the propery at all concentrations and Ts using the given function and insert it into self.egrid
        :param prop_name:
        :param prop_func (obj): the given function MUST takes c and T as required inputs in this order.
        :return:
        """
        if for_all_E:
            for tp in ["n", "p"]:
                self.egrid[tp][prop_name] = {
                c: {T: [self.gs for E in self.egrid[tp]["energy"]] for T in self.temperatures}
                for c in self.dopings}
        else:
            self.egrid[prop_name] = {c: {T: self.gs for T in self.temperatures} for c in self.dopings}
        for c in self.dopings:
            for T in self.temperatures:
                if for_all_E:
                    #fermi = self.egrid["fermi"][c][T]
                    fermi = self.fermi_level[c][T]
                    for tp in ["n", "p"]:
                        for ie, E in enumerate(self.egrid[tp]["energy"]):
                            self.egrid[tp][prop_name][c][T][ie] = prop_func(E, fermi, T)
                else:
                    self.egrid[prop_name][c][T] = prop_func(c, T)



    def calculate_N_II(self, c, T):
        """
        self.N_dis is a given observed 2D concentration of charged dislocations in 1/cm**2
        :param c:
        :param T:
        :return:
        """
        N_II = abs(self.egrid["calc_doping"][c][T]["n"]) * self.charge["n"] ** 2 + \
               abs(self.egrid["calc_doping"][c][T]["p"]) * self.charge["p"] ** 2 + \
               self.N_dis / self.volume ** (1 / 3) * 1e8 * self.charge["dislocations"] ** 2
        return N_II



    def init_egrid(self, dos_tp="simple"):
        """
        :param
            dos_tp (string): options are "simple", ...

        :return: an updated grid that contains the field DOS
        """

        self.egrid = {
            # "energy": {"n": [], "p": []},
            # "DOS": {"n": [], "p": []},
            # "all_en_flat": {"n": [], "p": []},
            "n": {"energy": [], "DOS": [], "all_en_flat": [], "all_ks_flat": []},
            "p": {"energy": [], "DOS": [], "all_en_flat": [], "all_ks_flat": []},
            "mobility": {}
        }
        self.kgrid_to_egrid_idx = {"n": [],
                                   "p": []}  # list of band and k index that are mapped to each memeber of egrid
        self.Efrequency = {"n": [], "p": []}
        self.sym_freq = {"n": [], "p":[]}
        # reshape energies of all bands to one vector:
        E_idx = {"n": [], "p": []}
        for tp in ["n", "p"]:
            for ib, en_vec in enumerate(self.kgrid[tp]["energy"]):
                self.egrid[tp]["all_en_flat"] += list(en_vec)
                self.egrid[tp]["all_ks_flat"] += list(self.kgrid[tp]["kpoints"][ib])
                # also store the flatten energy (i.e. no band index) as a tuple of band and k-indexes
                E_idx[tp] += [(ib, iek) for iek in range(len(en_vec))]

            # get the indexes of sorted flattened energy
            ieidxs = np.argsort(self.egrid[tp]["all_en_flat"])
            self.egrid[tp]["all_en_flat"] = [self.egrid[tp]["all_en_flat"][ie] for ie in ieidxs]
            self.egrid[tp]["all_ks_flat"] = [self.egrid[tp]["all_ks_flat"][ie] for ie in ieidxs]

            # sort the tuples of band and energy based on their energy
            E_idx[tp] = [E_idx[tp][ie] for ie in ieidxs]

        # setting up energy grid and DOS:
        for tp in ["n", "p"]:
            energy_counter = []
            i = 0
            last_is_counted = False
            while i < len(self.egrid[tp]["all_en_flat"]) - 1:
                sum_E = self.egrid[tp]["all_en_flat"][i]
                sum_nksym = len(self.remove_duplicate_kpoints(self.get_sym_eq_ks_in_first_BZ(self.egrid[tp]["all_ks_flat"][i])))
                counter = 1.0  # because the ith member is already included in sum_E
                current_ib_ie_idx = [E_idx[tp][i]]
                j = i
                # while j<len(self.egrid[tp]["all_en_flat"])-1 and (counter <= self.nE_min or \
                #         abs(self.egrid[tp]["all_en_flat"][i]-self.egrid[tp]["all_en_flat"][j+1]) < self.dE_min):
                while j < len(self.egrid[tp]["all_en_flat"]) - 1 and \
                        abs(self.egrid[tp]["all_en_flat"][i] - self.egrid[tp]["all_en_flat"][j + 1]) < self.dE_min:
                    # while i < len(self.egrid[tp]["all_en_flat"]) - 1 and \
                    #          self.egrid[tp]["all_en_flat"][i] == self.egrid[tp]["all_en_flat"][i + 1] :
                    counter += 1
                    current_ib_ie_idx.append(E_idx[tp][j + 1])
                    sum_E += self.egrid[tp]["all_en_flat"][j + 1]
                    sum_nksym += len(self.remove_duplicate_kpoints(self.get_sym_eq_ks_in_first_BZ(self.egrid[tp]["all_ks_flat"][i+1])))

                    if j + 1 == len(self.egrid[tp]["all_en_flat"]) - 1:
                        last_is_counted = True
                    j += 1
                self.egrid[tp]["energy"].append(sum_E / counter)
                self.kgrid_to_egrid_idx[tp].append(current_ib_ie_idx)
                self.sym_freq[tp].append(sum_nksym / counter)
                energy_counter.append(counter)

                if dos_tp.lower() == "simple":
                    self.egrid[tp]["DOS"].append(counter / len(self.egrid[tp]["all_en_flat"]))
                elif dos_tp.lower() == "standard":
                    self.egrid[tp]["DOS"].append(self.dos[self.get_Eidx_in_dos(sum_E / counter)][1])
                i = j + 1

            if not last_is_counted:
                self.egrid[tp]["energy"].append(self.egrid[tp]["all_en_flat"][-1])
                self.kgrid_to_egrid_idx[tp].append([E_idx[tp][-1]])
                if dos_tp.lower() == "simple":
                    self.egrid[tp]["DOS"].append(self.nelec / len(self.egrid[tp]["all_en_flat"]))
                elif dos_tp.lower() == "standard":
                    self.egrid[tp]["DOS"].append(self.dos[self.get_Eidx_in_dos(self.egrid[tp]["energy"][-1])][1])

            self.egrid[tp]["size"] = len(self.egrid[tp]["energy"])
            # if dos_tp.lower()=="standard":
            #     energy_counter = [ne/len(self.egrid[tp]["all_en_flat"]) for ne in energy_counter]
            # TODO: what is the best value to pick for width here?I guess the lower is more precisely at each energy?
            # dum, self.egrid[tp]["DOS"] = get_dos(self.egrid[tp]["energy"], energy_counter,width = 0.05)

        # logging.debug("here self.kgrid_to_egrid_idx: {}".format(self.kgrid_to_egrid_idx[self.debug_tp]))
        # logging.debug(self.kgrid[self.debug_tp]["energy"])


        for tp in ["n", "p"]:
            self.Efrequency[tp] = [len(Es) for Es in self.kgrid_to_egrid_idx[tp]]


        logging.debug("here total number of ks from self.Efrequency for {}-type".format(self.debug_tp))
        logging.debug(sum(self.Efrequency[self.debug_tp]))

        min_nE = 2

        if len(self.Efrequency["n"]) < min_nE or len(self.Efrequency["p"]) < min_nE:
            raise ValueError("The final egrid have fewer than {} energy values, AMSET stops now".format(min_nE))

        # initialize some fileds/properties
        self.egrid["calc_doping"] = {c: {T: {"n": 0.0, "p": 0.0} for T in self.temperatures} for c in self.dopings}
        for sn in self.elastic_scatterings + self.inelastic_scatterings + ["overall", "average", "SPB_ACD"]:
            # self.egrid["mobility"+"_"+sn]={c:{T:{"n": 0.0, "p": 0.0} for T in self.temperatures} for c in self.dopings}
            self.egrid["mobility"][sn] = {c: {T: {"n": 0.0, "p": 0.0} for T in self.temperatures} for c in self.dopings}
        for transport in ["conductivity", "J_th", "seebeck", "TE_power_factor", "relaxation time constant"]:
            self.egrid[transport] = {c: {T: {"n": 0.0, "p": 0.0} for T in self.temperatures} for c in self.dopings}

        # populate the egrid at all c and T with properties; they can be called via self.egrid[prop_name][c][T] later
        if self.fermi_calc_type == 'k':
            self.egrid["calc_doping"] = self.calc_doping
        if self.fermi_calc_type == 'e':
            self.calculate_property(prop_name="fermi", prop_func=self.find_fermi)
            self.fermi_level = self.egrid["fermi"]

        # self.egrid["fermi"]= {
        #              2000000000000000.0: {
        #                  300: -0.575512702461
        #              }
        #          }


        # Since the SPB generated band structure may have several valleys, it's better to use the Fermi calculated from the actual band structure
        # self.calculate_property(prop_name="fermi_SPB", prop_func=self.find_fermi_SPB)

        ##  in case specific fermi levels are to be tested:


        self.calculate_property(prop_name="f0", prop_func=f0, for_all_E=True)
        self.calculate_property(prop_name="f", prop_func=f0, for_all_E=True)
        self.calculate_property(prop_name="f_th", prop_func=f0, for_all_E=True)

        for prop in ["f", "f_th"]:
            self.map_to_egrid(prop_name=prop, c_and_T_idx=True)

        self.calculate_property(prop_name="f0x1-f0", prop_func=lambda E, fermi, T: f0(E, fermi, T)
                                                                                   * (1 - f0(E, fermi, T)),
                                for_all_E=True)

        for c in self.dopings:
            for T in self.temperatures:
                #fermi = self.egrid["fermi"][c][T]
                fermi = self.fermi_level[c][T]
                for tp in ["n", "p"]:
                    #fermi_norm = fermi - self.cbm_vbm[tp]["energy"]
                    for ib in range(len(self.kgrid[tp]["energy"])):
                        for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                            E = self.kgrid[tp]["energy"][ib][ik]
                            v = self.kgrid[tp]["velocity"][ib][ik]
                            self.kgrid[tp]["f0"][c][T][ib][ik] = f0(E, fermi, T) * 1.0

        self.calculate_property(prop_name="beta", prop_func=self.inverse_screening_length)

        # self.egrid["beta"]= {
        #             -1e+21: {
        #                 300: {
        #                     "n": 1.8402,
        #                     "p": 3.9650354562155636e-07
        #                 }
        #             },
        #             -1e+20: {
        #                 300: {
        #                     "n": 1.1615,
        #                     "p": 5.082645028590137e-06
        #                 }
        #             },
        #             -1e+19: {
        #                 300: {
        #                     "n": 0.6255,
        #                     "p": 1.8572918728014778e-05
        #                 }
        #             },
        #             -1e+18: {
        #                 300: {
        #                     "n": 0.2380,
        #                     "p": 5.956690579889094e-05
        #                 }
        #             }
        #         }

        self.calculate_property(prop_name="N_II", prop_func=self.calculate_N_II)
        self.calculate_property(prop_name="Seebeck_integral_numerator", prop_func=self.seeb_int_num)
        self.calculate_property(prop_name="Seebeck_integral_denominator", prop_func=self.seeb_int_denom)



    def get_Eidx_in_dos(self, E, Estep=None):
        if not Estep:
            Estep = max(self.dE_min, 0.0001)
        # there might not be anything wrong with the following but for now I thought using argmin() is safer
        # return int(round((E - self.dos_emin) / Estep))
        return abs(self.dos_emesh - E).argmin()

        # return min(int(round((E - self.dos_emin) / Estep)) , len(self.dos)-1)



    def G(self, tp, ib, ik, ib_prm, ik_prm, X):
        """
        The overlap integral betweek vectors k and k'
        :param ik (int): index of vector k in kgrid
        :param ik_prm (int): index of vector k' in kgrid
        :param X (float): cosine of the angle between vectors k and k'
        :return: overlap integral
        """
        a = self.kgrid[tp]["a"][ib][ik]
        c = self.kgrid[tp]["c"][ib][ik]
        return (a * self.kgrid[tp]["a"][ib_prm][ik_prm] + X * c * self.kgrid[tp]["c"][ib_prm][ik_prm]) ** 2



    def remove_indexes(self, rm_idx_list, rearranged_props):
        """
        The k-points with velocity < 1 cm/s (either in valence or conduction band) are taken out as those are
            troublesome later with extreme values (e.g. too high elastic scattering rates)
        :param rm_idx_list ([int]): the kpoint indexes that need to be removed for each property
        :param rearranged_props ([str]): list of properties for which some indexes need to be removed
        :return:
        """
        for i, tp in enumerate(["n", "p"]):
            for ib in range(self.cbm_vbm[tp]["included"]):
                rm_idx_list_ib = list(set(rm_idx_list[tp][ib]))
                rm_idx_list_ib.sort(reverse=True)
                rm_idx_list[tp][ib] = rm_idx_list_ib
                logging.debug("# of kpoints indexes with low velocity or off-energy: {}".format(len(rm_idx_list_ib)))
            for prop in rearranged_props:
                self.kgrid[tp][prop] = np.array([np.delete(self.kgrid[tp][prop][ib], rm_idx_list[tp][ib], axis=0) \
                                                 for ib in range(self.cbm_vbm[tp]["included"])])



    def initialize_var(self, grid, names, val_type="scalar", initval=0.0, is_nparray=True, c_T_idx=False):
        """
        initializes a variable/key within the self.kgrid variable
        :param grid (str): options are "kgrid" or "egrid": whether to initialize vars in self.kgrid or self.egrid
        :param names (list): list of the names of the variables
        :param val_type (str): options are "scalar", "vector", "matrix" or "tensor"
        :param initval (float): the initial value (e.g. if val_type=="vector", each of the vector's elements==init_val)
        :param is_nparray (bool): whether the final initial content is an numpy.array or not.
        :param c_T_idx (bool): whether to define the variable at each concentration, c, and temperature, T.
        :return:
        """
        if not isinstance(names, list):
            names = [names]

        if val_type.lower() in ["scalar"]:
            initial_val = initval
        elif val_type.lower() in ["vector"]:
            initial_val = [initval, initval, initval]
        elif val_type.lower() in ["tensor", "matrix"]:
            # initial_val = [ [initval, initval, initval], [initval, initval, initval], [initval, initval, initval] ]
            initial_val = [[initval for i in range(3)] for i in range(3)]

        for name in names:
            for tp in ["n", "p"]:
                self[grid][tp][name] = 0.0
                if grid in ["kgrid"]:
                    init_content = [[initial_val for i in range(len(self[grid][tp]["kpoints"][j]))]
                                    for j in range(self.cbm_vbm[tp]["included"])]
                elif grid in ["egrid"]:
                    init_content = [initial_val for i in range(len(self[grid][tp]["energy"]))]
                else:
                    raise TypeError('The argument "grid" must be set to either "kgrid" or "egrid"')
                if is_nparray:
                    if not c_T_idx:
                        self[grid][tp][name] = np.array(init_content)
                    else:
                        self[grid][tp][name] = {c: {T: np.array(init_content) for T in self.temperatures} for c in
                                                self.dopings}
                else:
                    # TODO: if not is_nparray both temperature values will be equal probably because both are equal to init_content that are a list and FOREVER they will change together. Keep is_nparray as True as it makes a copy, otherwise you are doomed! See if you can fix this later
                    if val_type not in ["scalar"] and c_T_idx:
                        raise ValueError(
                            "For now keep using is_nparray=True to see why for not is_nparray everything becomes equal at all temepratures (lists are not copied but they are all the same)")
                    else:
                        if not c_T_idx:
                            self[grid][tp][name] = init_content
                        else:
                            self[grid][tp][name] = {c: {T: init_content for T in self.temperatures} for c in
                                                    self.dopings}


    @staticmethod
    def remove_duplicate_kpoints(kpts, dk=0.0001):
        """kpts (list of list): list of coordinates of electrons
         ALWAYS return either a list or ndarray: BE CONSISTENT with the input!!!

         Attention: it is better to call this method only once as calculating the norms takes time.
         """
        start_time = time.time()

        rm_list = []

        kdist = [norm(k) for k in kpts]
        ktuple = zip(kdist, kpts)
        ktuple.sort(key=lambda x: x[0])
        kpts = [tup[1] for tup in ktuple]

        i = 0
        while i < len(kpts) - 1:
            j = i
            while j < len(kpts) - 1 and ktuple[j + 1][0] - ktuple[i][0] < dk:

                # for i in range(len(kpts)-2):
                # if kpts[i][0] == kpts[i+1][0] and kpts[i][1] == kpts[i+1][1] and kpts[i][2] == kpts[i+1][2]:

                if (abs(kpts[i][0] - kpts[j + 1][0]) < dk or abs(kpts[i][0]) == abs(kpts[j + 1][0]) == 0.5) and \
                        (abs(kpts[i][1] - kpts[j + 1][1]) < dk or abs(kpts[i][1]) == abs(kpts[j + 1][1]) == 0.5) and \
                        (abs(kpts[i][2] - kpts[j + 1][2]) < dk or abs(kpts[i][2]) == abs(kpts[j + 1][2]) == 0.5):
                    rm_list.append(j + 1)
                j += 1
            i += 1

        # The reason the following does NOT work is this example: [[0,3,4], [4,3,0], [0.001, 3, 4]]: In this example,
        # the k-points are correctly sorted based on their norm but 0&1 or 1&2 are NOT equal but 0&3 are but not captured
        # for i in range(len(kpts)-2):
        #     if (abs(kpts[i][0]-kpts[i+1][0])<dk or abs(kpts[i][0])==abs(kpts[i+1][0])==0.5) and \
        #             (abs(kpts[i][1]-kpts[i+1][1]) < dk or abs(kpts[i][1]) == abs(kpts[i+1][1]) == 0.5) and \
        #             (abs(kpts[i][2]-kpts[i+1][2]) < dk or abs(kpts[i][2]) == abs(kpts[i+1][2]) == 0.5):
        #             rm_list.append(i+1)

        kpts = np.delete(kpts, rm_list, axis=0)
        kpts = list(kpts)

        # even if this works (i.e. the shape of kpts is figured out, etc), it's not good as does not consider 0.0001 and 0.0002 equal
        # kpts = np.vstack({tuple(row) for row in kpts})


        # CORRECT BUT TIME CONSUMING WAY OF REMOVING DUPLICATES
        # for i in range(len(kpts)-2):
        #     # if abs(abs(kpts[i][0]) - 0.5) < 0.0001 and abs(abs(kpts[i][1]) - 0.5) < 0.0001 and abs(abs(kpts[i][2]) - 0.5) < 0.0001:
        #     #     rm_list.append(i)
        #     #     continue
        #     for j in range(i+1, len(kpts)-1):
        #         if (abs(kpts[i][0] - kpts[j][0]) < 0.0001 or abs(kpts[i][0])==abs(kpts[j][0])==0.5) and \
        #                 (abs(kpts[i][1] - kpts[j][1]) < 0.0001 or abs(kpts[i][1]) == abs(kpts[j][1]) == 0.5) and\
        #             (abs(kpts[i][2] - kpts[j][2]) < 0.0001 or abs(kpts[i][2]) == abs(kpts[j][2]) == 0.5):
        #
        #             rm_list.append(j)
        #
        # kpts = np.delete(kpts, rm_list, axis=0)
        # kpts = list(kpts)


        # print "total time to remove duplicate k-points = {} seconds".format(time.time() - start_time)
        # print "number of duplicates removed:"
        # print len(rm_list)

        return kpts



    def get_intermediate_kpoints(self, k1, k2, nsteps):
        """return a list nsteps number of k-points between k1 & k2 excluding k1 & k2 themselves. k1 & k2 are nparray"""
        dkii = (k2 - k1) / float(nsteps + 1)
        return [k1 + i * dkii for i in range(1, nsteps + 1)]



    def get_intermediate_kpoints_list(self, k1, k2, nsteps):
        """return a list nsteps number of k-points between k1 & k2 excluding k1 & k2 themselves. k1 & k2 are lists"""
        # dkii = (k2 - k1) / float(nsteps + 1)
        if nsteps < 1:
            return []
        dk = [(k2[i] - k1[i]) / float(nsteps + 1) for i in range(len(k1))]
        # return [k1 + i * dkii for i in range(1, nsteps + 1)]
        return [[k1[i] + n * dk[i] for i in range(len(k1))] for n in range(1, nsteps + 1)]



    @staticmethod
    def get_perturbed_ks(k):
        all_perturbed_ks = []
        # for p in [0.01, 0.03, 0.05]:
        for p in [0.05, 0.1]:
            all_perturbed_ks.append([k_i + p * np.sign(random() - 0.5) for k_i in k])
        return all_perturbed_ks



    def get_ks_with_intermediate_energy(self, kpts, energies, max_Ediff=None, target_Ediff=None):
        final_kpts_added = []
        target_Ediff = target_Ediff or self.dE_min
        for tp in ["n", "p"]:
            max_Ediff = max_Ediff or min(self.Ecut[tp], 10 * k_B * max(self.temperatures))
            if tp not in self.all_types:
                continue
            ies_sorted = list(np.argsort(energies[tp]))
            if tp == "p":
                ies_sorted.reverse()
            for idx, ie in enumerate(ies_sorted[:-1]):
                Ediff = abs(energies[tp][ie] - energies[tp][ies_sorted[0]])
                if Ediff > max_Ediff:
                    break
                final_kpts_added += self.get_perturbed_ks(kpts[ies_sorted[idx]])

                # final_kpts_added += self.get_intermediate_kpoints_list(list(kpts[ies_sorted[idx]]),
                #                                    list(kpts[ies_sorted[idx+1]]), max(int(Ediff/target_Ediff) , 1))
        return self.kpts_to_first_BZ(final_kpts_added)



    def get_adaptive_kpoints(self, kpts, energies, adaptive_Erange, nsteps):
        kpoints_added = {"n": [], "p": []}
        for tp in ["n", "p"]:
            if tp not in self.all_types:
                continue
            # TODO: if this worked, change it so that if self.dopings does not involve either of the types, don't add k-points for it
            ies_sorted = list(np.argsort(energies[tp]))
            if tp == "p":
                ies_sorted.reverse()
            for ie in ies_sorted:
                Ediff = abs(energies[tp][ie] - energies[tp][ies_sorted[0]])
                if Ediff >= adaptive_Erange[0] and Ediff < adaptive_Erange[-1]:
                    kpoints_added[tp].append(kpts[ie])

        print "here initial k-points for {}-type with low energy distance".format(self.debug_tp)
        print len(kpoints_added[self.debug_tp])
        # print kpoints_added[self.debug_tp]
        final_kpts_added = []
        for tp in ["n", "p"]:
            # final_kpts_added = []
            # TODO: in future only add the relevant k-poits for "kpoints" for each type separately
            # print kpoints_added[tp]
            for ik in range(len(kpoints_added[tp]) - 1):
                final_kpts_added += self.get_intermediate_kpoints_list(list(kpoints_added[tp][ik]),
                                                                       list(kpoints_added[tp][ik + 1]), nsteps)

        return self.kpts_to_first_BZ(final_kpts_added)



    def kpts_to_first_BZ(self, kpts):
        for i, k in enumerate(kpts):
            for alpha in range(3):
                if k[alpha] > 0.5:
                    k[alpha] -= 1
                if k[alpha] < -0.5:
                    k[alpha] += 1
            kpts[i] = k
        return kpts



    def get_sym_eq_ks_in_first_BZ(self, k, cartesian=False):
        """

        :param k (numpy.array): kpoint fractional coordinates
        :param cartesian (bool): if True, the output would be in cartesian (but still reciprocal) coordinates
        :return:
        """
        fractional_ks = [np.dot(k, self.rotations[i]) + self.translations[i] for i in range(len(self.rotations))]
        #TODO: not sure if I should include also the translations or not (see Si example to see if it makes a difference)
        # fractional_ks = [np.dot(k, self.rotations[i]) for i in range(len(self.rotations))]

        fractional_ks = self.kpts_to_first_BZ(fractional_ks)
        if cartesian:
            return [self._rec_lattice.get_cartesian_coords(k_frac) / A_to_nm for k_frac in fractional_ks]
        else:
            return fractional_ks



    # @albalu I created this function but do not understand what most of the arguments are. It may make sense to contain
    # them all in a single labeled tuple so the code is more readable?
    # engre through sgn: use for analytical bands energy; tp and ib: use for poly bands energy
    def calc_analytical_energy(self, xkpt, engre, nwave, nsym, nstv, vec, vec2, out_vec2, br_dir, sgn):
        """
            :param xkpt (?): ?
            :param engre (?): ?
            :param nwave (?): ?
            :param nsym (?): ?
            :param nstv (?): ?
            :param vec (?): ?
            :param vec2 (?): ?
            :param out_vec2 (?): ?
            :param br_dir (?): ?
            :param sgn (int): -1 or 1
        """
        energy, de, dde = get_energy(xkpt, engre, nwave, nsym, nstv, vec, vec2, out_vec2, br_dir=br_dir)
        energy = energy * Ry_to_eV - sgn * self.scissor / 2.0
        velocity = abs(de / hbar * A_to_m * m_to_cm * Ry_to_eV)
        effective_m = hbar ** 2 / (
            dde * 4 * pi ** 2) / m_e / A_to_m ** 2 * e * Ry_to_eV
        return energy, velocity, effective_m



    def calc_poly_energy(self, xkpt, tp, ib):
        '''
        :param tp: "p" or "n"
        :param ib: band index...?
        :return:
        '''
        energy, velocity, effective_m = get_poly_energy(
            self._rec_lattice.get_cartesian_coords(xkpt) / A_to_nm,
            poly_bands=self.poly_bands, type=tp, ib=ib, bandgap=self.dft_gap + self.scissor)
        return energy, velocity, effective_m



    # ultimately it might be most clean for this function to largely be two different functions (one for poly bands and one for analytical),
    # and then the parts they share can be separate functions called by both
    def init_kgrid(self, coeff_file, kgrid_tp="fine"):
        logging.debug("begin profiling the init_kgrid function")
        start_time = time.time()
        Tmx = max(self.temperatures)
        if kgrid_tp == "coarse":
            nkstep = self.nkibz

        sg = SpacegroupAnalyzer(self._vrun.final_structure)
        self.rotations, self.translations = sg._get_symmetry()  # this returns unique symmetry operations

        # logging.debug("rotation symmetry matrixes: \n {}".format(self.rotations))
        # logging.debug("translation symmetry matrixes: \n {}".format(self.translations))

        logging.info("self.nkibz = {}".format(self.nkibz))

        # TODO: the following is NOT a permanent solution to speed up generation/loading of k-mesh, speed up get_ir_reciprocal_mesh later
        # TODO-JF (mid-term): you can take on this project to speed up get_ir_reciprocal_mesh or a similar function, right now it scales very poorly with larger mesh

        # create a mesh of k-points
        # all_kpts = {}
        # try:
        #     ibzkpt_filename = os.path.join(os.environ["AMSET_ROOT"], "{}_ibzkpt_{}.json".format(nkstep,
        #                                                 self._vrun.final_structure.formula.replace(" ", "")))
        # except:
        #     ibzkpt_filename = "{}_ibzkpt.json".format(nkstep)
        # try:
        #     with open(ibzkpt_filename, 'r') as fp:
        #         all_kpts = json.load(fp, cls=MontyDecoder)
        #     kpts = all_kpts["{}x{}x{}".format(nkstep, nkstep, nkstep)]
        #     logging.info('reading {}x{}x{} k-mesh from "{}"'.format(nkstep, nkstep, nkstep, ibzkpt_filename))
        # except:
        #     logging.info('reading {} failed!'.format(ibzkpt_filename))
        #     logging.info("generating {}x{}x{} IBZ k-mesh".format(nkstep, nkstep, nkstep))
        #     # @albalu why is there an option to shift the k points and what are the weights?
        #     kpts_and_weights = sg.get_ir_reciprocal_mesh(mesh=(nkstep, nkstep, nkstep), is_shift=[0, 0, 0])
        #     # TODO: is_shift with 0.03 for y and 0.06 for z might give an error due to _all_elastic having twice length in kgrid compared to S_o, etc. I haven't figured out why
        #     # kpts_and_weights = sg.get_ir_reciprocal_mesh(mesh=(nkstep, nkstep, nkstep), is_shift=(0.00, 0.03, 0.06))
        #     kpts = [i[0] for i in kpts_and_weights]
        #     kpts = self.kpts_to_first_BZ(kpts)
        #     all_kpts["{}x{}x{}".format(nkstep, nkstep, nkstep)] = kpts
        #     with open(ibzkpt_filename, 'w') as fp:
        #         json.dump(all_kpts, fp, cls=MontyEncoder)

        bs_extrema = {"n": [self.cbm_vbm["n"]["kpoint"]],
                      "p": [self.cbm_vbm["p"]["kpoint"]]}
        nkk = 11
        kpts_and_weights = sg.get_ir_reciprocal_mesh(mesh=(nkk, nkk, nkk), is_shift=[0, 0, 0])
        initial_ibzkpt = [i[0] for i in kpts_and_weights]
        step_signs = [[np.sign(k[0]), np.sign(k[1]), np.sign(k[2])] for k in initial_ibzkpt]
        step_signs = self.remove_duplicate_kpoints(step_signs)
        print step_signs
        # kpts = [i[0] for i in kpts_and_weights]

        #adaptive k-mesh
        kpts = {tp: [self.cbm_vbm[tp]["kpoint"]] for tp in ["n", "p"]}

        # print "test!"
        # print self.rotations
        all_ibz = []
        # tk = 0.5
        # relevant_kpoints = [[0.0, 0.0, 0.0],  [tk, 0.0, 0.0], [tk, tk, 0.0], [-tk, tk, 0.0]]
        # for k in relevant_kpoints:
        #     all_ibz += [np.dot(k, self.rotations[i]) + self.translations[i] for i in range(len(self.rotations))]
        # all_ibz = self.kpts_to_first_BZ(all_ibz)
        # all_ibz = self.remove_duplicate_kpoints(all_ibz)
        # print all_ibz
        # print len(all_ibz)


        print "step_signs:", step_signs
        # test_signs = []
        # for i in [-1, 0, 1]:
        #     for j in [-1, 0, 1]:
        #         for k in [-1, 0, 1]:
        #             test_signs.append([i, j, k])

        # fine mesh
        # mesh =  in [[0.001, 10],[0.005, 10], [0.01, 21], [0.025, 21]]:
        # loose mesh
        # mesh = [[0.001, 5], [0.005, 10], [0.01, 10], [0.025, 10], [0.1, 5]]: # 1
        #     print "mesh: 1"
        #
        # mesh = [[0.001, 5], [0.005, 20], [0.01, 15], [0.025, 10], [0.1, 5]]: # 2
        #     print "mesh: 2"
        #
        # mesh =  [[0.001, 5], [0.005, 5], [0.01, 15], [0.025, 10], [0.1, 5]]: # 3
        #     print "mesh: 3"

        # mesh =  [[0.001, 5], [0.005, 5], [0.01, 20], [0.025, 10], [0.1, 5]]: # 4
        #     print "mesh: 4"

        # mesh =  [[0.001, 5], [0.005, 5], [0.01, 15], [0.025, 20]]: # 5
        #     print "mesh: 5"

        # mesh = [[0.001, 5], [0.005, 20], [0.01, 20], [0.025, 20]]: # 6
        #     print "mesh: 6"

        # mesh = [[0.001, 10], [0.005, 25], [0.01, 20], [0.025, 20]]: # 7
        #     print "mesh: 7"

        # mesh = [[0.001, 15], [0.005, 25], [0.01, 20], [0.025, 20]]: # 8
        #     print "mesh: 8"
        #
        # mesh = [[0.001, 5], [0.005, 10], [0.01, 10], [0.025, 20]]: # 9
        #     print "mesh: 9"
        #

        '''for step, nsteps in [[0.001, 5], [0.005, 10], [0.01, 5], [0.05, 11]]: # 10
        # if kgrid_tp == "fine":
        #     mesh = [[0.001, 5], [0.005, 10], [0.01, 5], [0.05, 11]] # 10
            print "mesh: 10"
        elif kgrid_tp == "coarse":
            mesh = [[0.002, 5], [0.01, 5], [0.05, 5], [0.25, 3]]
            print "mesh: 11"

        for tp in ["n", "p"]:
            for step, nsteps in mesh:
                for k_extremum in bs_extrema[tp]:
                    for kx_sign, ky_sign, kz_sign in step_signs:
                    # for kx_sign, ky_sign, kz_sign in test_signs:
                    # for kx_sign, ky_sign, kz_sign in [(1.0, 1.0, 1.0)]:
                        for kx in [k_extremum[0] + i*step*kx_sign for i in range(nsteps)]:
                            for ky in [k_extremum[1] + i * step*ky_sign for i in range(nsteps)]:
                                for kz in [k_extremum[2] + i * step*kz_sign for i in range(nsteps)]:
                                    kpts[tp].append([kx, ky, kz])
                                # kpts.append([-kx, ky, kz])
                                # kpts.append([kx, -ky, kz])
                                # kpts.append([kx, ky, -kz])
            # kpts[tp] = self.kpts_to_first_BZ(kpts[tp])
            # kpts[tp] = self.remove_duplicate_kpoints(kpts[tp])
        kpts = self.kpts_to_first_BZ(kpts)
        kpts = self.remove_duplicate_kpoints(kpts)'''


        # alternative version fo the above to create an appropriate kgrid for integration over k
        # start by producing a 1D list of values
        # setup a coarse "background" grid

        self.kgrid_array = {}

        #points_1d = {dir: [-0.4 + i*0.1 for i in range(9)] for dir in ['x', 'y', 'z']}
        #points_1d = {dir: [-0.475 + i * 0.05 for i in range(20)] for dir in ['x', 'y', 'z']}
        points_1d = {dir: [] for dir in ['x', 'y', 'z']}
        # TODO: figure out which other points need a fine grid around them
        important_pts = [self.cbm_vbm["n"]["kpoint"]]
        if (np.array(self.cbm_vbm["p"]["kpoint"]) != np.array(self.cbm_vbm["n"]["kpoint"])).any():
            important_pts.append(self.cbm_vbm["p"]["kpoint"])

        for center in important_pts:
            for dim, dir in enumerate(['x', 'y', 'z']):
                points_1d[dir].append(center[dim])
                one_list = True
                if not one_list:
                    #for step, nsteps in [[0.0015, 3], [0.005, 4], [0.01, 4], [0.05, 2]]:
                    for step, nsteps in [[0.002, 2], [0.005, 4], [0.01, 4], [0.05, 2]]:
                    #for step, nsteps in [[0.01, 2]]:
                        #print "mesh: 10"
                        # loop goes from 0 to nsteps-2, so added values go from step to step*(nsteps-1)
                        for i in range(nsteps - 1):
                            points_1d[dir].append(center[dim]-(i+1)*step)
                            points_1d[dir].append(center[dim]+(i+1)*step)

                else:
                    # set mesh
                    # number of points options are: 175,616, ~100,000, 74,088, 19,683, 15,625, 4,913, 125
                    #for step in [0.001, 0.002, 0.0035, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.018, 0.021, 0.025, 0.03, 0.035, 0.0425, 0.05, 0.06, 0.075, 0.1, 0.125, 0.15, 0.18, 0.21, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]:
                    #for step in [0.001, 0.002, 0.0035, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.0625, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]:
                    #for step in [0.001, 0.002, 0.0035, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.07, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]:
                    # this one is designed for n-GaAs at c = -3.3e13 at high temperatures like T=600 (not yet tested)
                    #for step in [0.001, 0.002, 0.0032, 0.005, 0.007, 0.009, 0.0115, 0.014, 0.0165, 0.0195, 0.0225, 0.026, 0.03, 0.035, 0.04, 0.05, 0.07, 0.1, 0.2, 0.3, 0.5]:
                    # this one is designed for n-GaAs at c = -3.3e13 (not much better than the poly_bands one)
                    #for step in [0.001, 0.002, 0.0032, 0.005, 0.007, 0.009, 0.0115, 0.014, 0.0165, 0.02, 0.025, 0.03, 0.04, 0.05, 0.07, 0.1, 0.2, 0.3, 0.5]:
                    # this one is designed for n-GaAs at c = -3.3e13 and is an experiment to see if large points are needed at all (changed results a lot)
                    #for step in [0.001, 0.002, 0.0032, 0.005, 0.007, 0.009, 0.0115, 0.014, 0.0165, 0.02, 0.025, 0.03, 0.04, 0.05, 0.07, 0.1, 0.5]:
                    # this one is designed for poly_bands
                    #for step in [0.001, 0.0025, 0.005, 0.007, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.07, 0.1, 0.2, 0.3, 0.5]:
                    #for step in [0.001, 0.0025, 0.005, (0.007), 0.01, 0.015, 0.02, (0.025), 0.03, (0.04), 0.05, (0.07), 0.1, 0.2, 0.3, --0.4, 0.5]:
                    #for step in [0.002, 0.005, 0.01, 0.015, 0.02, 0.03, 0.05, 0.1, 0.15, 0.25, 0.35, 0.5]:
                    # decent fine one
                    for step in [0.004, 0.01, 0.02, 0.03, 0.05, 0.07, 0.1, 0.15, 0.25, 0.35, 0.5]:
                    #for step in [0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.35, 0.45]:
                    #for step in [0.01, 0.025, 0.05, 0.1, 0.18, 0.3, 0.5]:
                    #for step in [0.004, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]:
                    # good coarse one
                    #for step in [0.01, 0.025, 0.05, 0.1, 0.25, 0.5]:
                    #for step in [0.15, 0.45]:
                    #for step in [0.003, 0.01, 0.02, 0.04]:
                        points_1d[dir].append(center[dim] + step)
                        points_1d[dir].append(center[dim] - step)

        logging.info('included points in the mesh: {}'.format(points_1d))

        # ensure all points are in "first BZ" (parallelepiped)
        for dir in ['x', 'y', 'z']:
            for ik1d in range(len(points_1d[dir])):
                if points_1d[dir][ik1d] > 0.5:
                    points_1d[dir][ik1d] -= 1
                if points_1d[dir][ik1d] < -0.5:
                    points_1d[dir][ik1d] += 1
        # remove duplicates
        for dir in ['x', 'y', 'z']:
            points_1d[dir] = list(set(np.array(points_1d[dir]).round(decimals=14)))
        self.kgrid_array['k_points'] = self.create_grid(points_1d)
        kpts = self.array_to_kgrid(self.kgrid_array['k_points'])

        N = self.kgrid_array['k_points'].shape
        self.k_hat_grid = np.zeros(N)
        for i in range(N[0]):
            for j in range(N[1]):
                for k in range(N[2]):
                    k_vec = self.kgrid_array['k_points'][i,j,k]
                    if norm(k_vec) == 0:
                        self.k_hat_grid[i,j,k] = [0, 0, 0]
                    else:
                        self.k_hat_grid[i,j,k] = k_vec / norm(k_vec)

        self.dv_grid = self.find_dv(self.kgrid_array['k_points'])



        # explicitly add the CBM/VBM k-points to calculate the parabolic band effective mass hence the relaxation time
        # kpts.append(self.cbm_vbm["n"]["kpoint"])
        # kpts.append(self.cbm_vbm["p"]["kpoint"])

        logging.info("number of original ibz k-points: {}".format(len(kpts)))
        # for tp in ["n", "p"]:
        #     logging.info("number of original {}-type, ibz k-points: {}".format(tp, len(kpts[tp])))
        logging.debug("time to get the ibz k-mesh: \n {}".format(time.time()-start_time))
        start_time = time.time()
        # TODO-JF: this if setup energy calculation for SPB and actual BS it would be nice to do this in two separate functions
        # if using analytical bands: create the object, determine list of band indices, and get energy info
        if not self.poly_bands:
            logging.debug("start interpolating bands from {}".format(coeff_file))
            analytical_bands = Analytical_bands(coeff_file=coeff_file)
            all_ibands = []
            for i, tp in enumerate(["p", "n"]):
                sgn = (-1) ** (i + 1)
                for ib in range(self.cbm_vbm[tp]["included"]):
                    all_ibands.append(self.cbm_vbm[tp]["bidx"] + sgn * ib)

            logging.debug("all_ibands: {}".format(all_ibands))

            # @albalu what are all of these variables (in the next 5 lines)? I don't know but maybe we can lump them together
            engre, latt_points, nwave, nsym, nsymop, symop, br_dir = analytical_bands.get_engre(iband=all_ibands)
            nstv, vec, vec2 = analytical_bands.get_star_functions(latt_points, nsym, symop, nwave, br_dir=br_dir)
            out_vec2 = np.zeros((nwave, max(nstv), 3, 3))
            for nw in xrange(nwave):
                for i in xrange(nstv[nw]):
                    out_vec2[nw, i] = outer(vec2[nw, i], vec2[nw, i])


        # if using poly bands, remove duplicate k points (@albalu I'm not really sure what this is doing)
        else:
            # first modify the self.poly_bands to include all symmetrically equivalent k-points (k_i)
            # these points will be used later to generate energy based on the minimum norm(k-k_i)
            for ib in range(len(self.poly_bands)):
                for j in range(len(self.poly_bands[ib])):
                    self.poly_bands[ib][j][0] = self.remove_duplicate_kpoints(
                        self.get_sym_eq_ks_in_first_BZ(self.poly_bands[ib][j][0], cartesian=True))

        logging.debug("time to get engre and calculate the outvec2: {} seconds".format(time.time() - start_time))

        # calculate only the CBM and VBM energy values - @albalu why is this separate from the other energy value calculations?
        # here we assume that the cbm and vbm k-point coordinates read from vasprun.xml are correct:

        for i, tp in enumerate(["p", "n"]):
            sgn = (-1) ** i

            if not self.poly_bands:
                energy, velocity, effective_m = self.calc_analytical_energy(self.cbm_vbm[tp]["kpoint"],
                                                                            engre[i * self.cbm_vbm["p"]["included"]],
                                                                            nwave, nsym, nstv, vec, vec2, out_vec2,
                                                                            br_dir, sgn)
            else:
                energy, velocity, effective_m = self.calc_poly_energy(self.cbm_vbm[tp]["kpoint"], tp, 0)

            # @albalu why is there already an energy value calculated from vasp that this code overrides?
            self.offset_from_vrun = energy - self.cbm_vbm[tp]["energy"]
            logging.debug("offset from vasprun energy values for {}-type = {} eV".format(tp, self.offset_from_vrun))
            self.cbm_vbm[tp]["energy"] = energy
            self.cbm_vbm[tp]["eff_mass_xx"] = effective_m.diagonal()

        if not self.poly_bands:
            self.dos_emax += self.offset_from_vrun
            self.dos_emin += self.offset_from_vrun

        logging.debug("cbm_vbm after recalculating their energy values:\n {}".format(self.cbm_vbm))
        self._avg_eff_mass = {tp: abs(np.mean(self.cbm_vbm[tp]["eff_mass_xx"])) for tp in ["n", "p"]}

        # calculate the energy at initial ibz k-points and look at the first band to decide on additional/adaptive ks
        start_time = time.time()
        energies = {"n": [0.0 for ik in kpts], "p": [0.0 for ik in kpts]}
        velocities = {"n": [[0.0, 0.0, 0.0] for ik in kpts], "p": [[0.0, 0.0, 0.0] for ik in kpts]}
        # energies = {"n": [0.0 for ik in kpts["n"]], "p": [0.0 for ik in kpts["n"]]}
        # velocities = {"n": [[0.0, 0.0, 0.0] for ik in kpts["n"]], "p": [[0.0, 0.0, 0.0] for ik in kpts["p"]]}
        rm_list = {"n": [], "p": []}

        # These two lines should be commented out when kpts is already for each carrier type
        kpts_copy = np.array(kpts)
        # The code below is not working right now - it is meant to speed up isotropic energy calculations (see below as well)
        # if self.bs_is_isotropic and not self.poly_bands:
        #     x_pos = kpts_copy[:, 0] >= 0
        #     y_pos = kpts_copy[:, 1] >= 0
        #     z_pos = kpts_copy[:, 2] >= 0
        #     x_y_pos = np.logical_and(x_pos, y_pos)
        #     all_pos = np.logical_and(x_y_pos, z_pos)
        #     kpts = {"n": np.array(kpts_copy[all_pos]), "p": np.array(kpts_copy[all_pos])}
        #     kpts_all_quads = {"n": np.array(kpts_copy), "p": np.array(kpts_copy)}
        # else:
        #     kpts = {"n": np.array(kpts_copy), "p": np.array(kpts_copy)}
        kpts = {"n": np.array(kpts_copy), "p": np.array(kpts_copy)}


        # self.kgrid = {
        #     "n": {},
        #     "p": {}}
        # for tp in ["n", "p"]:
        #     self.prop_list[tp]['kpoints'] = [kpts for ib in range(num_bands)]
        # self.kgrid[tp]["kpoints"] = [kpts[tp] for ib in range(num_bands)]

        self.pos_idx = {'n': [], 'p': []}


        self.num_bands = {tp: self.cbm_vbm[tp]["included"] for tp in ['n', 'p']}
        self.energy_array = {'n': [], 'p': []}

        # calculate energies
        for i, tp in enumerate(["p", "n"]):

            sgn = (-1) ** i
            for ib in range(self.cbm_vbm[tp]["included"]):
            # for ib in [0]:  # we only include the first band now (same for energies) to decide on ibz k-points
                if not self.parallel or self.poly_bands:  # The PB generator is fast enough no need for parallelization
                    for ik in range(len(kpts[tp])):
                        if not self.poly_bands:
                            energy, velocities[tp][ik], effective_m = self.calc_analytical_energy(kpts[tp][ik],engre[i * self.cbm_vbm[
                                "p"]["included"] + ib],nwave, nsym, nstv, vec, vec2,out_vec2, br_dir, sgn)
                        else:
                            energy, velocities[tp][ik], effective_m = self.calc_poly_energy(kpts[tp][ik], tp, ib)
                        energies[tp][ik] = energy

                        # @albalu why do we exclude values of k that have a small component of velocity?
                        # @Jason: because scattering equations have v in the denominator: get too large for such points
                        # if velocity[0] < self.v_min or velocity[1] < self.v_min or velocity[2] < self.v_min or \
                        #                 abs(energy - self.cbm_vbm[tp]["energy"]) > Ecut:
                        #     rm_list[tp].append(ik)
                else:
                    results = Parallel(n_jobs=self.num_cores)(delayed(get_energy)(kpts[tp][ik],engre[i * self.cbm_vbm["p"][
                        "included"] + ib], nwave, nsym, nstv, vec, vec2, out_vec2, br_dir) for ik in range(len(kpts[tp])))
                    for ik, res in enumerate(results):
                        energies[tp][ik] = res[0] * Ry_to_eV - sgn * self.scissor / 2.0
                        velocities[tp][ik] = abs(res[1] / hbar * A_to_m * m_to_cm * Ry_to_eV)
                        # if velocity[0] < self.v_min or velocity[1] < self.v_min or velocity[2] < self.v_min or \
                        #                 abs(energies[tp][ik] - self.cbm_vbm[tp]["energy"]) > Ecut:
                        #     # if tp=="p":
                        #     #     print "reason for removing the k-point:"
                        #     #     print "energy: {}".format(energies[tp][ik])
                        #     #     print "velocity: {}".format(velocity)
                        #     rm_list[tp].append(ik)

                self.energy_array[tp].append(self.grid_from_ordered_list(energies[tp], none_missing=True))

                if ib == 0:      # we only include the first band to decide on order of ibz k-points
                    e_sort_idx = np.array(energies[tp]).argsort() if tp == "n" else np.array(energies[tp]).argsort()[::-1]
                    energies[tp] = [energies[tp][ie] for ie in e_sort_idx]
                    velocities[tp] = [velocities[tp][ie] for ie in e_sort_idx]
                    self.pos_idx[tp] = np.array(range(len(e_sort_idx)))[e_sort_idx].argsort()
                    kpts[tp] = [kpts[tp][ie] for ie in e_sort_idx]

            # The code below is not working right now - it is meant to speed up isotropic energy calculations (see above as well)
            # if self.bs_is_isotropic and not self.poly_bands:
            #     # add the other quadrants back in
            #     for ib in [0]:#range(self.num_bands):
            #         for ik in range(len(kpts_all_quads[tp])):
            #             if not x_pos[ik]:
            #                 old_x = ik / (N[1] * N[2])
            #                 x_change = (N[0] - 1 - 2 * old_x) * N[1] * N[2]
            #             else:
            #                 x_change = 0
            #             if not y_pos[ik]:
            #                 old_y = (ik % (N[1] * N[2])) / N[2]
            #                 y_change = (N[1] - 1 - 2 * old_y) * N[2]
            #             else:
            #                 y_change = 0
            #             if not z_pos[ik]:
            #                 old_z = ik % N[2]
            #                 z_change = N[2] - 1 - 2 * old_z
            #             else:
            #                 z_change = 0
            #             new_idx = ik + x_change + y_change + z_change
            #             energies[tp][ik] = energies[tp][new_idx]
            #             velocities[tp][ik] = velocities[tp][new_idx]
            #
            #     kpts[tp] = kpts_all_quads[tp]

            # self.energy_array[tp] = [self.grid_from_ordered_list(energies[tp], none_missing=True) for ib in range(self.num_bands[tp])]

            # e_sort_idx = np.array(energies[tp]).argsort() if tp =="n" else np.array(energies[tp]).argsort()[::-1]

            # energies[tp] = [energies[tp][ie] for ie in e_sort_idx]

            # self.dos_end = max(energies["n"])
            # self.dos_start = min(energies["p"])

            # velocities[tp] = [velocities[tp][ie] for ie in e_sort_idx]
            # self.pos_idx[tp] = np.array(range(len(e_sort_idx)))[e_sort_idx].argsort()

            # kpts[tp] = [kpts[tp][ie] for ie in e_sort_idx]

        N = self.kgrid_array['k_points'].shape

        for ib in range(self.num_bands['n']):
            print('energy (type n, band {}):'.format(ib))
            print(self.energy_array['n'][ib][(N[0] - 1) / 2, (N[1] - 1) / 2, :])

        logging.debug("time to calculate ibz energy, velocity info and store them to variables: \n {}".format(time.time()-start_time))
        start_time = time.time()
        #TODO: the following for-loop is crucial but undone! it decides which k-points remove for speed and accuracy
        '''for tp in ["p", "n"]:
            Ecut = self.Ecut[tp]
            Ediff_old = 0.0
            # print "{}-type all Ediffs".format(tp)
            for ib in [0]:
                ik = -1
                # for ik in range(len(kpts[tp])):
                while ik < len(kpts[tp])-1:
                    ik += 1
                    Ediff = abs(energies[tp][ik] - self.cbm_vbm[tp]["energy"])
                    if Ediff > Ecut:
                        rm_list[tp] += range(ik, len(kpts[tp]))
                        break  # because the energies are sorted so after this point all energy points will be off
                    if velocities[tp][ik][0] < self.v_min or velocities[tp][ik][1] < self.v_min or\
                                    velocities[tp][ik][2] < self.v_min:
                        rm_list[tp].append(ik)

                    # the following if implements an adaptive dE_min as higher energy points are less important
                    #TODO: note that if k-mesh integration on a regular grid (not tetrahedron) is implemented, the
                    #TODO:following will make the results wrong as in that case we would assume the removed points are 0
                    while ik < len(kpts[tp])-1 and \
                            (Ediff > Ecut/5.0 and Ediff - Ediff_old < min(self.dE_min*10.0, 0.001) or
                            (Ediff > Ecut / 2.0 and Ediff - Ediff_old < min(self.dE_min * 100.0,0.01))):
                        rm_list[tp].append(ik)
                        ik += 1
                        Ediff = abs(energies[tp][ik] - self.cbm_vbm[tp]["energy"])

                    # if Ediff>Ecut/5.0 and Ediff - Ediff_old < min(self.dE_min*10.0, 0.001):
                            # or \
                            # Ediff>Ecut/2.0 and Ediff - Ediff_old < min(self.dE_min*100.0, 0.01):
                        # rm_list[tp].append(ik)
                    Ediff_old = Ediff

            rm_list[tp] = list(set(rm_list[tp]))'''

        logging.debug("time to filter energies from ibz k-mesh: \n {}".format(time.time()-start_time))
        start_time = time.time()
        # this step is crucial in DOS normalization when poly_bands to cover the whole energy range in BZ
        if self.poly_bands:
            all_bands_energies = {"n": [], "p": []}
            for tp in ["p", "n"]:
                all_bands_energies[tp] = energies[tp]
                for ib in range(1, len(self.poly_bands)):
                    for ik in range(len(kpts[tp])):
                        energy, velocity, effective_m = get_poly_energy(
                            self._rec_lattice.get_cartesian_coords(kpts[ik]) / A_to_nm,
                            poly_bands=self.poly_bands, type=tp, ib=ib, bandgap=self.dft_gap + self.scissor)
                        all_bands_energies[tp].append(energy)
            self.dos_emin = min(all_bands_energies["p"])
            self.dos_emax = max(all_bands_energies["n"])

        # logging.debug("energies before removing k-points with off-energy:\n {}".format(energies))
        # remove energies that are out of range



        # print "n-rm_list"
        # print rm_list["n"]
        # print "p-rm_list"
        # print rm_list["p"]
        '''
        for tp in ["n", "p"]:
            # if tp in self.all_types:
            if True:
                kpts[tp] = list(np.delete(kpts[tp], rm_list[tp], axis=0))
                # energies[tp] = np.delete(energies[tp], rm_list[tp], axis=0)
            else: # in this case it doesn't matter if the k-mesh is loose
                kpts[tp] = list(np.delete(kpts[tp], rm_list["n"]+rm_list["p"], axis=0))
                # energies[tp] = np.delete(energies[tp], rm_list["n"]+rm_list["p"], axis=0)
            if len(kpts[tp]) > 10000:
                warnings.warn("Too desne of a {}-type k-mesh (nk={}!); AMSET will be slow!".format(tp, len(kpts[tp])))

            logging.info("number of {}-type ibz k-points AFTER ENERGY-FILTERING: {}".format(tp, len(kpts[tp])))'''

        # 2 lines debug printing
        # energies["n"].sort()
        # print "{}-type energies for ibz after filtering: \n {}".format("n", energies["n"])
        del energies, velocities, e_sort_idx

        # TODO-JF (long-term): adaptive mesh is a good idea but current implementation is useless, see if you can come up with better method after talking to me
        if self.adaptive_mesh:
            raise IOError("adaptive mesh has not yet been implemented, please check back later!")
        #
        # if self.adaptive_mesh:
        #     all_added_kpoints = []
        #     all_added_kpoints += self.get_adaptive_kpoints(kpts, energies,
        #                                                    adaptive_Erange=[0 * k_B * Tmx, 1 * k_B * Tmx], nsteps=30)
        #
        #     # it seems it works mostly at higher energy values!
        #     # all_added_kpoints += self.get_ks_with_intermediate_energy(kpts,energies)
        #
        #     print "here the number of added k-points"
        #     print len(all_added_kpoints)
        #     print all_added_kpoints
        #     print type(kpts)
        #     kpts += all_added_kpoints

        # add in symmetrically equivalent k points
        # for tp in ["n", "p"]:
        #     symmetrically_equivalent_ks = []
        #     for k in kpts[tp]:
        #         symmetrically_equivalent_ks += self.get_sym_eq_ks_in_first_BZ(k)
        #     kpts[tp] += symmetrically_equivalent_ks
        #     kpts[tp] = self.remove_duplicate_kpoints(kpts[tp])
        #
        #
        #     if len(kpts[tp]) < 3:
        #         raise ValueError("The k-point mesh for {}-type is too loose (number of kpoints = {}) "
        #                         "after filtering the initial k-mesh".format(tp, len(kpts)))
        #
        #     logging.info("number of {}-type k-points after symmetrically equivalent kpoints are added: {}".format(
        #                 tp, len(kpts[tp])))

        # TODO: remove anything with "weight" later if ended up not using weights at all!
        kweights = {tp: [1.0 for i in kpts[tp]] for tp in ["n", "p"]}




        # logging.debug("time to add the symmetrically equivalent k-points: \n {}".format(time.time() - start_time))
        # start_time = time.time()

        # actual initiation of the kgrid
        self.kgrid = {
            "n": {},
            "p": {}}

        self.num_bands = {"n": {}, "p": {}}

        for tp in ["n", "p"]:
            self.num_bands[tp] = self.cbm_vbm[tp]["included"]
            self.kgrid[tp]["kpoints"] = [kpts[tp] for ib in range(self.num_bands[tp])]
            self.kgrid[tp]["kweights"] = [kweights[tp] for ib in range(self.num_bands[tp])]
            # self.kgrid[tp]["kpoints"] = [[k for k in kpts] for ib in range(self.cbm_vbm[tp]["included"])]
            # self.kgrid[tp]["kweights"] = [[kw for kw in kweights] for ib in range(self.cbm_vbm[tp]["included"])]

        self.initialize_var("kgrid", ["energy", "a", "c", "norm(v)", "norm(k)"], "scalar", 0.0, is_nparray=False, c_T_idx=False)
        self.initialize_var("kgrid", ["velocity"], "vector", 0.0, is_nparray=False, c_T_idx=False)
        self.initialize_var("kgrid", ["effective mass"], "tensor", 0.0, is_nparray=False, c_T_idx=False)

        start_time = time.time()

        rm_idx_list = {"n": [[] for i in range(self.cbm_vbm["n"]["included"])],
                       "p": [[] for i in range(self.cbm_vbm["p"]["included"])]}
        # @albalu why are these variables initialized separately from the ones above?
        self.initialize_var("kgrid", ["old cartesian kpoints", "cartesian kpoints"], "vector", 0.0, is_nparray=False, c_T_idx=False)
        self.initialize_var("kgrid", ["norm(k)", "norm(actual_k)"], "scalar", 0.0, is_nparray=False, c_T_idx=False)

        logging.debug("The DFT gap right before calculating final energy values: {}".format(self.dft_gap))

        for i, tp in enumerate(["p", "n"]):
            self.cbm_vbm[tp]["cartesian k"] = self._rec_lattice.get_cartesian_coords(self.cbm_vbm[tp]["kpoint"])/A_to_nm
            self.cbm_vbm[tp]["all cartesian k"] = self.get_sym_eq_ks_in_first_BZ(self.cbm_vbm[tp]["kpoint"], cartesian=True)
            self.cbm_vbm[tp]["all cartesian k"] = self.remove_duplicate_kpoints(self.cbm_vbm[tp]["all cartesian k"])

            sgn = (-1) ** i
            for ib in range(self.cbm_vbm[tp]["included"]):
                self.kgrid[tp]["old cartesian kpoints"][ib] = self._rec_lattice.get_cartesian_coords(
                    self.kgrid[tp]["kpoints"][ib]) / A_to_nm

                # REMEMBER TO MAKE A COPY HERE OTHERWISE THEY CHANGE TOGETHER
                self.kgrid[tp]["cartesian kpoints"][ib] = np.array(self.kgrid[tp]["old cartesian kpoints"][ib])
                # [1/nm], these are PHYSICS convention k vectors (with a factor of 2 pi included)

                if self.parallel and not self.poly_bands:
                    results = Parallel(n_jobs=self.num_cores)(delayed(get_energy)(self.kgrid[tp]["kpoints"][ib][ik],
                             engre[i * self.cbm_vbm["p"]["included"] + ib], nwave, nsym, nstv, vec, vec2, out_vec2,
                             br_dir) for ik in range(len(self.kgrid[tp]["kpoints"][ib])))

                s_orbital, p_orbital = self.get_dft_orbitals(bidx=self.cbm_vbm[tp]["bidx"] - 1 - sgn * ib)
                orbitals = {"s": s_orbital, "p": p_orbital}
                fit_orbs = {orb: griddata(points=np.array(self.DFT_cartesian_kpts), values=np.array(orbitals[orb]),
                    xi=np.array(self.kgrid[tp]["old cartesian kpoints"][ib]), method='nearest') for orb in orbitals.keys()}

                # TODO-JF: the general function for calculating the energy, velocity and effective mass can b
                for ik in range(len(self.kgrid[tp]["kpoints"][ib])):

                    min_dist_ik = np.array([norm(ki - self.kgrid[tp]["old cartesian kpoints"][ib][ik]) for ki in\
                                           self.cbm_vbm[tp]["all cartesian k"]]).argmin()
                    self.kgrid[tp]["cartesian kpoints"][ib][ik] = self.kgrid[tp]["old cartesian kpoints"][ib][ik] - \
                                                                  self.cbm_vbm[tp]["all cartesian k"][min_dist_ik]


                    self.kgrid[tp]["norm(k)"][ib][ik] = norm(self.kgrid[tp]["cartesian kpoints"][ib][ik])
                    self.kgrid[tp]["norm(actual_k)"][ib][ik] = norm(self.kgrid[tp]["old cartesian kpoints"][ib][ik])

                    if not self.poly_bands:
                        if not self.parallel:
                            energy, de, dde = get_energy(
                                self.kgrid[tp]["kpoints"][ib][ik], engre[i * self.cbm_vbm["p"]["included"] + ib],
                                nwave, nsym, nstv, vec, vec2, out_vec2, br_dir=br_dir)
                            energy = energy * Ry_to_eV - sgn * self.scissor / 2.0
                            velocity = abs(de / hbar * A_to_m * m_to_cm * Ry_to_eV)  # to get v in cm/s
                            effective_mass = hbar ** 2 / (
                                dde * 4 * pi ** 2) / m_e / A_to_m ** 2 * e * Ry_to_eV  # m_tensor: the last part is unit conversion
                        else:
                            energy = results[ik][0] * Ry_to_eV - sgn * self.scissor / 2.0
                            velocity = abs(results[ik][1] / hbar * A_to_m * m_to_cm * Ry_to_eV)
                            effective_mass = hbar ** 2 / (
                                results[ik][
                                    2] * 4 * pi ** 2) / m_e / A_to_m ** 2 * e * Ry_to_eV  # m_tensor: the last part is unit conversion

                    else:
                        energy, velocity, effective_mass = get_poly_energy(self.kgrid[tp]["old cartesian kpoints"][ib][ik],
                                                                           poly_bands=self.poly_bands,
                                                                           type=tp, ib=ib,
                                                                           bandgap=self.dft_gap + self.scissor)

                    self.kgrid[tp]["energy"][ib][ik] = energy
                    self.kgrid[tp]["velocity"][ib][ik] = velocity
                    self.kgrid[tp]["norm(v)"][ib][ik] = norm(velocity)

                    # self.kgrid[tp]["velocity"][ib][ik] = de/hbar * A_to_m * m_to_cm * Ry_to_eV # to get v in units of cm/s
                    # TODO: what's the implication of negative group velocities? check later after scattering rates are calculated
                    # TODO: actually using abs() for group velocities mostly increase nu_II values at each energy
                    # TODO: should I have de*2*pi for the group velocity and dde*(2*pi)**2 for effective mass?
                    if self.kgrid[tp]["velocity"][ib][ik][0] < self.v_min or  \
                                    self.kgrid[tp]["velocity"][ib][ik][1] < self.v_min \
                            or self.kgrid[tp]["velocity"][ib][ik][2] < self.v_min or \
                                    abs(self.kgrid[tp]["energy"][ib][ik] - self.cbm_vbm[tp]["energy"]) > self.Ecut[tp]:
                        rm_idx_list[tp][ib].append(ik)
                    # else:
                        # print "this point remains in {}-type: extrema, current energy. ib, ik: {}, {}".format(tp,ib,ik)
                        # , self.cbm_vbm[tp]["energy"], self.kgrid[tp]["energy"][ib][ik]

                    # TODO: AF must test how large norm(k) affect ACD, IMP and POP and see if the following is necessary
                    # if self.kgrid[tp]["norm(k)"][ib][ik] > 5:
                    #     rm_idx_list[tp][ib].append(ik)

                    self.kgrid[tp]["effective mass"][ib][ik] = effective_mass

                    if self.poly_bands:
                        self.kgrid[tp]["a"][ib][ik] = 1.0 # parabolic band s-orbital only
                        self.kgrid[tp]["c"][ib][ik] = 0.0
                    else:
                        self.kgrid[tp]["a"][ib][ik] = fit_orbs["s"][ik]/ (fit_orbs["s"][ik]**2 + fit_orbs["p"][ik]**2)**0.5
                        self.kgrid[tp]["c"][ib][ik] = (1 - self.kgrid[tp]["a"][ib][ik]**2)**0.5

            logging.debug("average of the {}-type group velocity in kgrid:\n {}".format(
                        tp, np.mean(self.kgrid[self.debug_tp]["velocity"][0], 0)))

        rearranged_props = ["velocity", "effective mass", "energy", "a", "c", "kpoints", "cartesian kpoints",
                            "old cartesian kpoints", "kweights",
                            "norm(v)", "norm(k)", "norm(actual_k)"]

        # print('Check -1: kgrid energy:')
        # print(np.array(self.kgrid['n']['energy'][0])[0:20])
        # print('unsorted energy:')
        # print(np.array(self.kgrid['n']['energy'][0])[self.pos_idx][0:20])

        logging.debug("time to calculate E, v, m_eff at all k-points: \n {}".format(time.time()-start_time))
        start_time = time.time()
        # print('check 0')
        # print(self.array_from_kgrid('cartesian kpoints', 'n', none_missing=True)[0, 4, :, :, 1])
        # TODO: the following is temporary, for some reason if # of kpts in different bands are NOT the same,
        # I get an error that _all_elastic is a list! so 1/self.kgrid[tp]["_all_elastic"][c][T][ib] cause error int/list!
        # that's why I am removing indexes from the first band at all bands! this is temperary
        # suggested solution: make the band index a key in the dictionary of kgrid rather than list index so we
        # can treat each band independently without their dimensions required to match!
        # TODO-AF or TODO-JF (mid-term): set the band index as a key in dictionary throughout AMSET to enable independent modification of bands information
        for tp in ["n", "p"]:
            rm_idx_list[tp] = [rm_idx_list[tp][0] for ib in range(self.cbm_vbm[tp]["included"])]
        # print('check 0')
        #print(self.array_from_kgrid('cartesian kpoints', 'n', none_missing=True)[0, 4, :, :, 1])
        # print(self.array_from_kgrid('energy', 'n', none_missing=True)[0, 4, :, :, 0])
        self.rm_idx_list = deepcopy(rm_idx_list)   # format: [tp][ib][ik]
        # print('self.rm_idx_list:')
        # print(self.rm_idx_list['n'])
        # print('kgrid energy before removal:')
        # print(np.array(self.kgrid['n']['energy'][0])[0:20])
        # remove the k-points with off-energy values (>Ecut away from CBM/VBM) that are not removed already
        self.remove_indexes(rm_idx_list, rearranged_props=rearranged_props)
        # print('self.rm_idx_list after removal:')
        # print(self.rm_idx_list['n'])
        # print('kgrid energy after removal:')
        # print(np.array(self.kgrid['n']['energy'][0])[0:20])
        # print('check 1')
        # print(self.array_from_kgrid('cartesian kpoints', 'n')[0, 4, :, :, 1])
        # print(self.array_from_kgrid('energy', 'n')[0, 4, :, :, 0])
        logging.debug("dos_emin = {} and dos_emax= {}".format(self.dos_emin, self.dos_emax))

        for tp in ["n", "p"]:
            for ib in range(len(self.kgrid[tp]["energy"])):
                logging.info("Final # of {}-kpts in band #{}: {}".format(tp, ib, len(self.kgrid[tp]["kpoints"][ib])))

            if len(self.kgrid[tp]["kpoints"][0]) < 5:
                raise ValueError("VERY BAD {}-type k-mesh; please change the k-mesh and try again!".format(tp))

        logging.debug("time to calculate energy, velocity, m* for all: {} seconds".format(time.time() - start_time))
        # print('check 1')
        # print(self.array_from_kgrid('cartesian kpoints', 'n')[0, 4, :, :, 1])
        #print('list of initial energies before sort 2:')
        #print(self.kgrid['n']['energy'][0])
        # sort "energy", "kpoints", "kweights", etc based on energy in ascending order and keep track of old indexes
        e_sort_idx_2 = self.sort_vars_based_on_energy(args=rearranged_props, ascending=True)
        self.pos_idx_2 = deepcopy(e_sort_idx_2)
        for tp in ['n', 'p']:
            for ib in range(self.num_bands[tp]):
                self.pos_idx_2[tp][ib] = np.array(range(len(e_sort_idx_2[tp][ib])))[e_sort_idx_2[tp][ib]].argsort()
        #print('check 1')
        #print(self.array_from_kgrid('cartesian kpoints', 'n')[0, 4, :, :, 1])
        # to save memory avoiding storage of variables that we don't need down the line
        for tp in ["n", "p"]:
            self.kgrid[tp].pop("effective mass", None)
            self.kgrid[tp].pop("kweights", None)
            self.kgrid[tp]["size"] = [len(self.kgrid[tp]["kpoints"][ib]) \
                                      for ib in range(len(self.kgrid[tp]["kpoints"]))]

        self.initialize_var("kgrid", ["W_POP"], "scalar", 0.0, is_nparray=True, c_T_idx=False)
        self.initialize_var("kgrid", ["N_POP"], "scalar", 0.0, is_nparray=True, c_T_idx=True)

        for tp in ["n", "p"]:
            for ib in range(self.cbm_vbm[tp]["included"]):
                # TODO: change how W_POP is set, user set a number or a file that can be fitted and inserted to kgrid
                self.kgrid[tp]["W_POP"][ib] = [self.W_POP for i in range(len(self.kgrid[tp]["kpoints"][ib]))]
                for c in self.dopings:
                    for T in self.temperatures:
                        self.kgrid[tp]["N_POP"][c][T][ib] = np.array(
                            [1 / (np.exp(hbar * W_POP / (k_B * T)) - 1) for W_POP in self.kgrid[tp]["W_POP"][ib]])

        self.initialize_var(grid="kgrid", names=["_all_elastic", "S_i", "S_i_th", "S_o", "S_o_th", "g", "g_th", "g_POP",
                                                 "f", "f_th", "relaxation time", "df0dk", "electric force",
                                                 "thermal force"],
                            val_type="vector", initval=self.gs, is_nparray=True, c_T_idx=True)

        self.initialize_var("kgrid", ["f0", "f_plus", "f_minus", "g_plus", "g_minus"], "vector", self.gs,
                            is_nparray=True, c_T_idx=True)
        # self.initialize_var("kgrid", ["lambda_i_plus", "lambda_i_minus"]
        #                     , "vector", self.gs, is_nparray=True, c_T_idx=False)


        # x = 4
        # print(self._rec_lattice.matrix)
        # print(self._rec_lattice.get_cartesian_coords([0, 0, -0.1]))
        # print(self._rec_lattice.get_cartesian_coords([0, 0, 0]))
        # print(self._rec_lattice.get_cartesian_coords([0, 0, 0.1]))
        # print(self._rec_lattice.get_cartesian_coords([0, 0, 0.2]))
        # print(self._rec_lattice.get_cartesian_coords([[0, 0, 0.1], [0, 0, 0.2]]))
        # energy_grid = self.array_from_kgrid('energy', 'n')
        # print('energy:')
        # np.set_printoptions(precision=3)
        # print(energy_grid[0, x, :, :, 0])
        # print('cartesian k points')
        # print(self.array_from_kgrid('old cartesian kpoints', 'n')[0, x, :, :, 0]**2 + self.array_from_kgrid('old cartesian kpoints', 'n')[0, x, :, :, 1]**2 + self.array_from_kgrid('old cartesian kpoints', 'n')[0, x, :, :, 2]**2)
        # print(self.array_from_kgrid('cartesian kpoints', 'n')[0, x, :, :, 0]**2 + self.array_from_kgrid('cartesian kpoints', 'n')[0, x, :, :, 1]**2 + self.array_from_kgrid('cartesian kpoints', 'n')[0, x, :, :, 2]**2)
        # print(self.array_from_kgrid('cartesian kpoints', 'n')[0, x, :, :, 0])
        # print(self.array_from_kgrid('cartesian kpoints', 'n')[0, x, :, :, 1])
        # print(self.array_from_kgrid('cartesian kpoints', 'n')[0, x, :, :, 2])
        # print('k points')
        # print(self.kgrid_array['k_points'][x, :, :, 0])
        # print(self.kgrid_array['k_points'][x, :, :, 1])
        # print(self.kgrid_array['k_points'][x, :, :, 2])
        # np.set_printoptions(precision=8)

        # calculation of the density of states (DOS)
        if not self.poly_bands:
            emesh, dos, dos_nbands, bmin = analytical_bands.get_dos_from_scratch(self._vrun.final_structure,
                                                                           [self.nkdos, self.nkdos, self.nkdos],
                                                                           self.dos_emin, self.dos_emax,
                                                                           int(round(
                                                                               (self.dos_emax - self.dos_emin) / max(
                                                                                   self.dE_min, 0.0001))),
                                                                           width=self.dos_bwidth, scissor=self.scissor,
                                                                           vbmidx=self.cbm_vbm["p"]["bidx"])
            logging.debug("dos_nbands: {} \n".format(dos_nbands))
            self.dos_normalization_factor = dos_nbands if self.soc else dos_nbands * 2
            # self.dos_normalization_factor = self.nbands*2 if not self.soc else self.nbands

            self.dos_start = min(self._vrun.get_band_structure().as_dict()["bands"]["1"][bmin]) \
                             + self.offset_from_vrun - self.scissor/2.0
            self.dos_end = max(self._vrun.get_band_structure().as_dict()["bands"]["1"][bmin+dos_nbands]) \
                           + self.offset_from_vrun + self.scissor / 2.0
        else:
            logging.debug("here self.poly_bands: \n {}".format(self.poly_bands))
            emesh, dos = get_dos_from_poly_bands(self._vrun.final_structure, self._rec_lattice,
                                                 [self.nkdos, self.nkdos, self.nkdos], self.dos_emin, self.dos_emax,
                                                 int(round(
                                                     (self.dos_emax - self.dos_emin) / max(self.dE_min, 0.0001))),
                                                 poly_bands=self.poly_bands,
                                                 bandgap=self.cbm_vbm["n"]["energy"] - self.cbm_vbm["p"][
                                                     "energy"],  # we include here the actual or after-scissor gap here
                                                 width=self.dos_bwidth, SPB_DOS=False)
            self.dos_normalization_factor = len(
                self.poly_bands) * 2 * 2  # it is *2 elec/band & *2 because DOS is repeated in valence/conduction
            self.dos_start = self.dos_emin
            self.dos_end = self.dos_emax


        print("DOS normalization factor: {}".format(self.dos_normalization_factor))
        # print("The actual emsh used for dos normalization: {}".format(emesh))
        # print("The actual dos: {}".format(dos))

        integ = 0.0
        # for idos in range(len(dos) - 2):

        # here is the dos normalization story: to normalize DOS we first calculate the integral of the following two
        # energy ranges (basically the min and max of the original energy range) and normalize it based on the DOS
        # that is generated for a limited number of bands.

        self.dos_start = abs(emesh - self.dos_start).argmin()
        self.dos_end = abs(emesh - self.dos_end).argmin()

        # self.dos_start = 0
        # self.dos_end = len(dos) - 1
        for idos in range(self.dos_start, self.dos_end):
            # if emesh[idos] > self.cbm_vbm["n"]["energy"]: # we assume anything below CBM as 0 occupation
            #     break
            integ += (dos[idos + 1] + dos[idos]) / 2 * (emesh[idos + 1] - emesh[idos])

        print "dos integral from {} index to {}: {}".format(self.dos_start,  self.dos_end, integ)

        # normalize DOS
        # logging.debug("dos before normalization: \n {}".format(zip(emesh, dos)))
        dos = [g / integ * self.dos_normalization_factor for g in dos]
        # logging.debug("integral of dos: {} stoped at index {} and energy {}".format(integ, idos, emesh[idos]))

        self.dos = zip(emesh, dos)
        self.dos_emesh = np.array(emesh)
        self.vbm_dos_idx = self.get_Eidx_in_dos(self.cbm_vbm["p"]["energy"])
        self.cbm_dos_idx = self.get_Eidx_in_dos(self.cbm_vbm["n"]["energy"])

        print("vbm and cbm DOS index")
        print self.vbm_dos_idx
        print self.cbm_dos_idx
        # logging.debug("full dos after normalization: \n {}".format(self.dos))
        # logging.debug("dos after normalization from vbm idx to cbm idx: \n {}".format(self.dos[self.vbm_dos_idx-10:self.cbm_dos_idx+10]))

        self.dos = [list(a) for a in self.dos]

        logging.debug("time to finish the remaining part of init_kgrid: \n {}".format(time.time() - start_time))


    def sort_vars_based_on_energy(self, args, ascending=True):
        """sort the list of variables specified by "args" (type: [str]) in self.kgrid based on the "energy" values
        in each band for both "n"- and "p"-type bands and in ascending order by default."""
        ikidxs = {'n': {ib: [] for ib in range(self.num_bands['n'])}, 'p': {ib: [] for ib in range(self.num_bands['p'])}}
        for tp in ["n", "p"]:
            for ib in range(self.cbm_vbm[tp]["included"]):
                ikidxs[tp][ib] = np.argsort(self.kgrid[tp]["energy"][ib])
                if not ascending:
                    ikidxs[tp][ib].reverse()
                for arg in args:
                    self.kgrid[tp][arg][ib] = np.array([self.kgrid[tp][arg][ib][ik] for ik in ikidxs[tp][ib]])
        return ikidxs



    def generate_angles_and_indexes_for_integration(self, avg_Ediff_tolerance=0.02):
        """
        generates the indexes of k' points that have the same energy (for elastic scattering) as E(k) or
        have energy equal to E(k) plus or minus of the energy of the optical phonon for inelastic scattering.
        Also, generated and stored the cosine of the angles between such points and a given input k-point

        Args:
            avg_Ediff_tolerance (float): in eV the average allowed energy difference between the target E(k') and
                what it actially is (e.g. to prevent/identify large energy differences if enforced scattering)
        """
        self.initialize_var("kgrid", ["X_E_ik", "X_Eplus_ik", "X_Eminus_ik"], "scalar", [], is_nparray=False,
                            c_T_idx=False)

        # elastic scattering
        for tp in ["n", "p"]:
            for ib in range(len(self.kgrid[tp]["energy"])):
                self.nforced_scat = {"n": 0.0, "p": 0.0}
                self.ediff_scat = {"n": [], "p": []}
                for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                    self.kgrid[tp]["X_E_ik"][ib][ik] = self.get_X_ib_ik_near_new_E(tp, ib, ik,
                            E_change=0.0, forced_min_npoints=2, tolerance=self.dE_min)
                enforced_ratio = self.nforced_scat[tp] / sum([len(points) for points in self.kgrid[tp]["X_E_ik"][ib]])
                logging.info("enforced scattering ratio for {}-type elastic scattering at band {}:\n {}".format(
                        tp, ib, enforced_ratio))
                if enforced_ratio > 0.9:
                    # TODO: this should be an exception but for now I turned to warning for testing.
                    warnings.warn("the k-grid is too coarse for an acceptable simulation of elastic scattering in {};"
                        .format(self.tp_title[tp]))

                avg_Ediff = sum(self.ediff_scat[tp]) / max(len(self.ediff_scat[tp]), 1)
                if avg_Ediff > avg_Ediff_tolerance:
                    #TODO: change it back to ValueError as it was originally, it was switched to warning for fast debug
                    warnings.warn("{}-type average energy difference of the enforced scattered k-points is more than"
                                  " {}, try running with a more dense k-point mesh".format(tp, avg_Ediff_tolerance))

        # inelastic scattering
        if "POP" in self.inelastic_scatterings:
            for tp in ["n", "p"]:
                sgn = (-1) ** (["n", "p"].index(tp))
                for ib in range(len(self.kgrid[tp]["energy"])):
                    self.nforced_scat = {"n": 0.0, "p": 0.0}
                    self.ediff_scat = {"n": [], "p": []}
                    for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                        self.kgrid[tp]["X_Eplus_ik"][ib][ik] = self.get_X_ib_ik_near_new_E(tp, ib, ik,
                                E_change= + hbar * self.kgrid[tp]["W_POP"][ib][ik],forced_min_npoints=2,
                                   tolerance=self.dE_min)
                        self.kgrid[tp]["X_Eminus_ik"][ib][ik] = self.get_X_ib_ik_near_new_E(tp, ib, ik,
                                E_change= - hbar * self.kgrid[tp]["W_POP"][ib][ik],forced_min_npoints=2,
                                        tolerance=self.dE_min)
                    enforced_ratio = self.nforced_scat[tp] / (
                        sum([len(points) for points in self.kgrid[tp]["X_Eplus_ik"][ib]]) + \
                        sum([len(points) for points in self.kgrid[tp]["X_Eminus_ik"][ib]]))
                    logging.info(
                        "enforced scattering ratio: {}-type inelastic at band {}:\n{}".format(tp, ib, enforced_ratio))

                    if enforced_ratio > 0.9:
                        # TODO: this should be an exception but for now I turned to warning for testing.
                        warnings.warn(
                            "the k-grid is too coarse for an acceptable simulation of POP scattering in {};"
                            " you can try this k-point grid but without POP as an inelastic scattering.".format(
                                self.tp_title[tp]))

                    avg_Ediff = sum(self.ediff_scat[tp]) / max(len(self.ediff_scat[tp]), 1)
                    if avg_Ediff > avg_Ediff_tolerance:
                        # TODO: this should be an exception but for now I turned to warning for testing.
                        warnings.warn(
                            "{}-type average energy difference of the enforced scattered k-points is more than"
                            " {}, try running with a more dense k-point mesh".format(tp, avg_Ediff_tolerance))



    def unique_X_ib_ik_symmetrically_equivalent(self, tp, ib, ik):
        frac_k = self.kgrid[tp]["kpoints"][ib][ik]

        fractional_ks = [np.dot(frac_k, self.rotations[i]) + self.translations[i] for i in range(len(self.rotations))]

        k = self.kgrid[tp]["kpoints"][ib][ik]
        seks = [self._rec_lattice.get_cartesian_coords(frac_k) / A_to_nm for frac_k in fractional_ks]

        all_Xs = []
        new_X_ib_ik = []
        for sek in seks:
            X = cos_angle(k, sek)
            if X in all_Xs:
                continue
            else:
                new_X_ib_ik.append((X, ib, ik, sek))
                all_Xs.append(X)
        all_Xs.sort()
        return new_X_ib_ik


    def get_X_ib_ik_near_new_E(self, tp, ib, ik, E_change, forced_min_npoints=0, tolerance=0.01):
        """Returns the sorted (based on angle, X) list of angle and band and k-point indexes of all the points
            that are within tolerance of E + E_change
            Attention!!! this function assumes self.kgrid is sorted based on the energy in ascending order.
        Args:
            tp (str): type of the band; options: "n" or "p"
            ib (int): the band index
            ik (int): the k-point index
            E_change (float): the difference between E(k') and E(k)
            forced_min_npoints (int): the number of k-points that are forcefully included in
                scattering if not enough points are found
            tolerance (float): the energy tolerance for finding the k' points that are within E_change energy of E(k)
            """
        E = self.kgrid[tp]["energy"][ib][ik]
        E_prm = E + E_change  # E_prm is E prime, the new energy
        k = self.kgrid[tp]["cartesian kpoints"][ib][ik]
        # we count the point itself; it does not result in self-scattering (due to 1-X term); however, it is necessary
        # to avoid zero scattering as in the integration each term is (X[i+1]-X[i])*(integrand[i]+integrand[i+1)/2
        result = [(1, ib, ik)]

        nk = len(self.kgrid[tp]["kpoints"][ib])

        for ib_prm in range(self.cbm_vbm[tp]["included"]):
            # this code is commented out because it is unnecessary unless it saves a lot of time
            # if ib==ib_prm and E_change==0.0:
            #    ik_closest_E = ik
            # else:
            ik_closest_E = np.abs(self.kgrid[tp]["energy"][ib_prm] - E_prm).argmin()

            for step, start in [(1, 0), (-1, -1)]:
                ik_prm = ik_closest_E + start  # go up from ik_closest_E, down from ik_closest_E - 1
                while ik_prm >= 0 and ik_prm < nk and abs(self.kgrid[tp]["energy"][ib_prm][ik_prm] - E_prm) < tolerance:
                    X_ib_ik = (cos_angle(k, self.kgrid[tp]["cartesian kpoints"][ib_prm][ik_prm]), ib_prm, ik_prm)
                    if (X_ib_ik[1], X_ib_ik[2]) not in [(entry[1], entry[2]) for entry in result]:
                        result.append(X_ib_ik)
                    ik_prm += step

        # If fewer than forced_min_npoints number of points were found, just return a few surroundings of the same band
        ib_prm = ib
        # if E_change == 0.0:
        #    ik_closest_E = ik
        # else:
        ik_closest_E = np.abs(self.kgrid[tp]["energy"][ib_prm] - E_prm).argmin()

        for step, start in [(1, 0), (-1, -1)]:
            # step -1 is in case we reached the end (ik_prm == nk - 1); then we choose from the lower energy k-points
            ik_prm = ik_closest_E + start  # go up from ik_closest_E, down from ik_closest_E - 1
            while ik_prm >= 0 and ik_prm < nk and len(result) - 1 < forced_min_npoints:
                # add all the k-points that have the same energy as E_prime E(k_pm); these values are stored in X_E_ik
                # @albalu isn't this the function that is used to generate self.kgrid[tp]["X_E_ik"]? How will there already be something in self.kgrid[tp]["X_E_ik"] at this point?
                for X_ib_ik in self.kgrid[tp]["X_E_ik"][ib_prm][ik_prm]:
                    X, ib_pmpm, ik_pmpm = X_ib_ik
                    X_ib_ik_new = (
                    cos_angle(k, self.kgrid[tp]["cartesian kpoints"][ib_pmpm][ik_pmpm]), ib_pmpm, ik_pmpm)
                    if (X_ib_ik_new[1], X_ib_ik_new[2]) not in [(entry[1], entry[2]) for entry in result]:
                        result.append(X_ib_ik_new)
                    self.nforced_scat[tp] += 1

                self.ediff_scat[tp].append(
                    self.kgrid[tp]["energy"][ib][ik] - self.kgrid[tp]["energy"][ib_prm][ik_prm])
                ik_prm += step

        result.sort(key=lambda x: x[0])
        return result



    def s_el_eq(self, sname, tp, c, T, k, k_prm):
        """
        return the scattering rate at wave vector k at a certain concentration and temperature
        for a specific elastic scattering mechanisms determined by sname

        Args:
        sname (string): abbreviation of the name of the elastic scatteirng mechanisms; options: IMP, ADE, PIE, DIS
        c (float): carrier concentration
        T (float): the temperature
        k (list): list containing fractional coordinates of the k vector
        k_prm (list): list containing fractional coordinates of the k prime vector
        """

        norm_diff_k = norm(k - k_prm)  # the slope for PIE and IMP don't match with bs_is_isotropic

        if norm_diff_k == 0.0:
            warnings.warn("WARNING!!! same k and k' vectors as input of the elastic scattering equation")
            return 0.0

        if sname.upper() in ["IMP"]:  # ionized impurity scattering
            unit_conversion = 0.001 / e ** 2
            return unit_conversion * e ** 4 * self.egrid["N_II"][c][T] / \
                   (4.0 * pi ** 2 * self.epsilon_s ** 2 * epsilon_0 ** 2 * hbar) \
                   / ((norm_diff_k ** 2 + self.egrid["beta"][c][T][tp] ** 2) ** 2)

        elif sname.upper() in ["ACD"]:  # acoustic deformation potential scattering
            unit_conversion = 1e18 * e
            return unit_conversion * k_B * T * self.E_D[tp] ** 2 / (4.0 * pi ** 2 * hbar * self.C_el)

        elif sname.upper() in ["PIE"]:  # piezoelectric scattering
            unit_conversion = 1e9 / e
            return unit_conversion * e ** 2 * k_B * T * self.P_PIE ** 2 \
                   / (norm_diff_k ** 2 * 4.0 * pi ** 2 * hbar * epsilon_0 * self.epsilon_s)

        elif sname.upper() in ["DIS"]:
            return self.gs

        else:
            raise ValueError("The elastic scattering name {} is not supported!".format(sname))



    def integrate_over_DOSxE_dE(self, func, tp, fermi, T, interpolation_nsteps=None, normalize_energy=False):
        if not interpolation_nsteps:
            interpolation_nsteps = max(200, int(500.0 / len(self.egrid[tp]["energy"])))
        integral = 0.0
        for ie in range(len(self.egrid[tp]["energy"]) - 1):
            E = self.egrid[tp]["energy"][ie]
            dE = (self.egrid[tp]["energy"][ie + 1] - E) / interpolation_nsteps
            if normalize_energy:
                E -= self.cbm_vbm[tp]["energy"]
                fermi -= self.cbm_vbm[tp]["energy"]
            dS = (self.egrid[tp]["DOS"][ie + 1] - self.egrid[tp]["DOS"][ie]) / interpolation_nsteps
            for i in range(interpolation_nsteps):
                # integral += dE * (self.egrid[tp]["DOS"][ie] + i * dS)*func(E + i * dE, fermi, T)*self.Efrequency[tp][ie]
                integral += dE * (self.egrid[tp]["DOS"][ie] + i * dS) * func(E + i * dE, fermi, T)
        return integral
        # return integral/sum(self.Efrequency[tp][:-1])



    # points_1d now a dictionary with 'x', 'y', and 'z' lists of points
    # points_1d lists do not need to be sorted
    def create_grid(self, points_1d):
        for dir in ['x', 'y', 'z']:
            points_1d[dir].sort()
        grid = np.zeros((len(points_1d['x']), len(points_1d['y']), len(points_1d['z']), 3))
        for i, x in enumerate(points_1d['x']):
            for j, y in enumerate(points_1d['y']):
                for k, z in enumerate(points_1d['z']):
                    grid[i, j, k, :] = np.array([x, y, z])
        return grid


    # grid is a 4d numpy array, where last dimension is vectors in a 3d grid specifying fractional position in BZ
    def array_to_kgrid(self, grid):
        kgrid = []
        for i in range(grid.shape[0]):
            for j in range(grid.shape[1]):
                for k in range(grid.shape[2]):
                    kgrid.append(grid[i,j,k])
        return kgrid


    def grid_index_from_list_index(self, list_index):
        N = self.kgrid_array['k_points'].shape
        count = list_index
        i, j, k = (0,0,0)
        while count >= N[2]*N[1]:
            count -= N[2]*N[1]
            i += 1
        while count >= N[2]:
            count -= N[2]
            j += 1
        k = count
        return (i,j,k)


    def find_dv(self, grid):
        dv = np.zeros(grid[:, :, :, 0].shape)
        # N is a vector of the number of x, y, and z points
        N = grid.shape

        for i in range(N[0]):
            for j in range(N[1]):
                for k in range(N[2]):
                    if i > 0:
                        dx1 = (grid[i,j,k,0] - grid[i-1,j,k,0]) / 2
                    else:
                        dx1 = grid[i,j,k,0] - (-0.5)
                    if i < N[0] - 1:
                        dx2 = (grid[i+1,j,k,0] - grid[i,j,k,0]) / 2
                    else:
                        dx2 = 0.5 - grid[i,j,k,0]

                    if j > 0:
                        dy1 = (grid[i,j,k,1] - grid[i,j-1,k,1]) / 2
                    else:
                        dy1 = grid[i,j,k,1] - (-0.5)
                    if j < N[1] - 1:
                        dy2 = (grid[i,j+1,k,1] - grid[i,j,k,1]) / 2
                    else:
                        dy2 = 0.5 - grid[i,j,k,1]

                    if k > 0:
                        dz1 = (grid[i,j,k,2] - grid[i,j,k-1,2]) / 2
                    else:
                        dz1 = grid[i,j,k,2] - (-0.5)
                    if k < N[2] - 1:
                        dz2 = (grid[i,j,k+1,2] - grid[i,j,k,2]) / 2
                    else:
                        dz2 = 0.5 - grid[i,j,k,2]
                    # find fractional volume
                    dv[i,j,k] = (dx1 + dx2) * (dy1 + dy2) * (dz1 + dz2)

        # convert from fractional to cartesian (k space) volume
        dv *= self._rec_lattice.volume / (A_to_m * m_to_cm) ** 3

        return dv


    # takes a coordinate grid in the form of a numpy array (CANNOT have missing points) and a function to integrate and
    # finds the integral using finite differences; missing points should be input as 0 in the function
    def integrate_over_k(self, func_grid):#, xDOS=False, xvel=False, weighted=True):
        '''
        :return: result of the integral
        '''

        # in the interest of not prematurely optimizing, func_grid must be a perfect grid: the only deviation from
        # the cartesian coordinate system can be uniform stretches, as in the distance between adjacent planes of points
        # can be any value, but no points can be missing from the next plane

        # in this case the format of fractional_grid is a 4d grid
        # the last dimension is a vector of the k point fractional coordinates
        # the dv grid is 3d and the indexes correspond to those of func_grid

        if func_grid.ndim == 3:
            return np.sum(func_grid * self.dv_grid)
        return [np.sum(func_grid[:,:,:,i] * self.dv_grid) for i in range(func_grid.shape[3])]



    def integrate_over_BZ(self, prop_list, tp, c, T, xDOS=False, xvel=False, weighted=True):

        weighted = False

        """

        :param tp:
        :param c:
        :param T:
        :param distribution (str): can be switched between f, f0, g, g_POP, etc
        :param xvel:
        :return:
        """
        wpower = 1
        if xvel:
            wpower += 1
        integral = np.array([self.gs, self.gs, self.gs])
        for ie in range(len(self.egrid[tp]["energy"]) - 1):
            dE = abs(self.egrid[tp]["energy"][ie + 1] - self.egrid[tp]["energy"][ie])
            sum_over_k = np.array([self.gs, self.gs, self.gs])
            for ib, ik in self.kgrid_to_egrid_idx[tp][ie]:
                k_nrm = self.kgrid[tp]["norm(k)"][ib][ik]
                # k_nrm = norm(self.kgrid[tp]["old cartesian kpoints"][ib][ik])

                # 4*pi, hbar and norm(v) are coming from the conversion of dk to dE
                product = k_nrm ** 2 / self.kgrid[tp]["norm(v)"][ib][ik] * 4 * pi / hbar
                # product = 1.0
                if xvel:
                    product *= self.kgrid[tp]["velocity"][ib][ik]
                for j, p in enumerate(prop_list):
                    if p[0] == "/":
                        product /= self.kgrid[tp][p.split("/")[-1]][c][T][ib][ik]
                    elif p[0] == "1":  # this assumes that the property is 1-f0 for example
                        product *= 1 - self.kgrid[tp][p.split("-")[-1].replace(" ", "")][c][T][ib][ik]
                    else:
                        product *= self.kgrid[tp][p][c][T][ib][ik]
                sum_over_k += product
            # if not weighted:
            #     sum_over_k /= len(self.kgrid_to_egrid_idx[tp][ie])
            if xDOS:
                sum_over_k *= self.egrid[tp]["DOS"][ie]
            if weighted:
            #     sum_over_k *= self.Efrequency[tp][ie] ** (wpower)
                sum_over_k *=self.Efrequency[tp][ie] / float(self.sym_freq[tp][ie])
            integral += sum_over_k * dE

        if weighted:
            return integral
            # return integral / sum([freq ** (wpower) for freq in self.Efrequency[tp][:-1]])
        else:
            return integral
            # return integral / sum([self.egrid[tp]["f0"][c][T][ie][0]*self.Efrequency[tp][ie] for ie in range(len(self.Efrequency[tp][:-1]))])



    def integrate_over_normk(self, prop_list, tp, c, T, xDOS, interpolation_nsteps=None):
        integral = self.gs
        normk_tp = "norm(k)"
        if not interpolation_nsteps:
            interpolation_nsteps = max(200, int(500.0 / len(self.kgrid[tp]["kpoints"][0])))
        for ib in [0]:
            # normk_sorted_idx = np.argsort([norm(k) for k in self.kgrid[tp]["old cartesian kpoints"][ib]])
            normk_sorted_idx = np.argsort(self.kgrid[tp][normk_tp][ib])
            diff = [0.0 for prop in prop_list]


            for j, ik in enumerate(normk_sorted_idx[:-1]):
                ik_next = normk_sorted_idx[j+1]
                normk = self.kgrid[tp][normk_tp][ib][ik]
                dk = (self.kgrid[tp][normk_tp][ib][ik_next] - normk)/interpolation_nsteps
                if dk == 0.0:
                    continue
                # print normk
                # print dk
                if xDOS:
                    dS = ((self.kgrid[tp][normk_tp][ib][ik_next]/pi)**2 - \
                         (self.kgrid[tp][normk_tp][ib][ik]/pi)**2)/interpolation_nsteps
                for j, p in enumerate(prop_list):
                    if p[0] == "/":
                        diff[j] = (self.kgrid[tp][p.split("/")[-1]][c][T][ib][ik_next] - \
                                        self.kgrid[tp][p.split("/")[-1]][c][T][ib][ik]) / interpolation_nsteps
                    elif p[0] == "1":
                        diff[j] = ((1 - self.kgrid[tp][p.split("-")[-1].replace(" ", "")][c][T][ib][ik_next]) - \
                                  (1 - self.kgrid[tp][p.split("-")[-1].replace(" ", "")][c][T][ib][ik])) / interpolation_nsteps
                    else:
                        diff[j] = (self.kgrid[tp][p][c][T][ib][ik_next] - self.kgrid[tp][p][c][T][ib][ik]) / interpolation_nsteps
                    # product *= (self.kgrid[tp][p][c][T][ib][ik+1] + self.kgrid[tp][p][c][T][ib][ik])/2


                for i in range(interpolation_nsteps):
                    multi = dk
                    for j, p in enumerate(prop_list):
                        if p[0] == "/":
                            multi /= self.kgrid[tp][p.split("/")[-1]][c][T][ib][ik] + diff[j] * i
                        elif "1" in p:
                            multi *= 1 - self.kgrid[tp][p.split("-")[-1].replace(" ", "")][c][T][ib][ik] + diff[j] * i
                        else:
                            multi *= self.kgrid[tp][p][c][T][ib][ik] + diff[j] * i
                    if xDOS:
                        multi *= (self.kgrid[tp][normk_tp][ib][ik]/pi)**2 + dS * i
                    integral += multi

        # print "sorted cartesian kpoints for {}-type: {}".format(tp,[self.kgrid[tp]["old cartesian kpoints"][ib][ik] for ik in normk_sorted_idx])
        # print "sorted cartesian kpoints for {}-type: {}".format(tp,[self.kgrid[tp]["norm(actual_k)"][ib][ik] for ik in normk_sorted_idx])
        return integral



    def integrate_over_E(self, prop_list, tp, c, T, xDOS=False, xvel=False, weighted=False, interpolation_nsteps=None):

        # for now I keep weighted as False, to re-enable weighting, all GaAs tests should be re-evaluated.

        weighted = False

        wpower = 1
        if xvel:
            wpower += 1
        imax_occ = len(self.Efrequency[tp][:-1])

        if not interpolation_nsteps:
            interpolation_nsteps = max(200, int(500.0 / len(self.egrid[tp]["energy"])))
            # interpolation_nsteps = 1
        diff = [0.0 for prop in prop_list]
        integral = self.gs
        # for ie in range(len(self.egrid[tp]["energy"]) - 1):
        for ie in range(imax_occ):

            E = self.egrid[tp]["energy"][ie]
            dE = abs(self.egrid[tp]["energy"][ie + 1] - E) / interpolation_nsteps
            if xDOS:
                dS = (self.egrid[tp]["DOS"][ie + 1] - self.egrid[tp]["DOS"][ie]) / interpolation_nsteps
            if xvel:
                dv = (self.egrid[tp]["velocity"][ie + 1] - self.egrid[tp]["velocity"][ie]) / interpolation_nsteps
            for j, p in enumerate(prop_list):
                if "/" in p:
                    diff[j] = (self.egrid[tp][p.split("/")[-1]][c][T][ie + 1] -
                               self.egrid[tp][p.split("/")[-1]][c][T][ie]) / interpolation_nsteps
                elif "1 -" in p:
                    diff[j] = (1 - self.egrid[tp][p.split("-")[-1].replace(" ", "")][c][T][ie + 1] - (1- \
                               self.egrid[tp][p.split("-")[-1].replace(" ", "")][c][T][ie])) / interpolation_nsteps
                else:
                    diff[j] = (self.egrid[tp][p][c][T][ie + 1] - self.egrid[tp][p][c][T][ie]) / interpolation_nsteps
            if weighted:
                dweight = (self.Efrequency[tp][ie+1] / float(self.sym_freq[tp][ie+1]) - \
                          self.Efrequency[tp][ie] / float(self.sym_freq[tp][ie]) ) /interpolation_nsteps
            for i in range(interpolation_nsteps):
                multi = dE
                for j, p in enumerate(prop_list):
                    if p[0] == "/":
                        multi /= self.egrid[tp][p.split("/")[-1]][c][T][ie] + diff[j] * i
                    elif "1 -" in p:
                        multi *= 1 - self.egrid[tp][p.split("-")[-1].replace(" ", "")][c][T][ie] + diff[j] * i
                    else:
                        multi *= self.egrid[tp][p][c][T][ie] + diff[j] * i
                if xDOS:
                    multi *= self.egrid[tp]["DOS"][ie] + dS * i
                if xvel:
                    multi *= self.egrid[tp]["velocity"][ie] + dv * i
                if weighted:
                    # integral += multi * self.Efrequency[tp][ie]**wpower * (-(dfdE + ddfdE))
                    # integral += multi * self.Efrequency[tp][ie]**wpower *dfdE
                    # integral += multi * self.Efrequency[tp][ie]**wpower * self.egrid[tp]["f0"][c][T][ie]
                    # integral += multi * self.Efrequency[tp][ie] ** wpower
                    integral += multi * (self.Efrequency[tp][ie] / float(self.sym_freq[tp][ie]) + dweight * i)
                else:
                    integral += multi
        if weighted:
            return integral
            # return integral/(sum(self.Efrequency[tp][:-1]))

        else:
            return integral



    def integrate_over_X(self, tp, X_E_index, integrand, ib, ik, c, T, sname=None, g_suffix=""):
        """integrate numerically with a simple trapezoidal algorithm."""
        summation = np.array([0.0, 0.0, 0.0])
        if len(X_E_index[ib][ik]) == 0:
            raise ValueError("enforcing scattering points did NOT work, {}[{}][{}] is empty".format(X_E_index, ib, ik))
            # return summation
        X, ib_prm, ik_prm = X_E_index[ib][ik][0]
        current_integrand = integrand(tp, c, T, ib, ik, ib_prm, ik_prm, X, sname=sname, g_suffix=g_suffix)
        for i in range(len(X_E_index[ib][ik]) - 1):
            DeltaX = X_E_index[ib][ik][i + 1][0] - X_E_index[ib][ik][i][0]
            if DeltaX == 0.0:
                continue

            X, ib_prm, ik_prm = X_E_index[ib][ik][i + 1]

            dum = current_integrand / 2.0

            current_integrand = integrand(tp, c, T, ib, ik, ib_prm, ik_prm, X, sname=sname, g_suffix=g_suffix)

            # This condition is to exclude self-scattering from the integration
            if np.sum(current_integrand) == 0.0:
                dum *= 2
            elif np.sum(dum) == 0.0:
                dum = current_integrand
            else:
                dum += current_integrand / 2.0

            summation += dum * DeltaX  # In case of two points with the same X, DeltaX==0 so no duplicates
        return summation



    def el_integrand_X(self, tp, c, T, ib, ik, ib_prm, ik_prm, X, sname=None, g_suffix=""):

        # The following (if passed on to s_el_eq) result in many cases k and k_prm being equal which we don't want.
        # k = m_e * self._avg_eff_mass[tp] * self.kgrid[tp]["norm(v)"][ib][ik] / (hbar * e * 1e11)
        # k_prm = m_e * self._avg_eff_mass[tp] * self.kgrid[tp]["normv"][ib_prm][ik_prm] / (hbar * e * 1e11)

        k = self.kgrid[tp]["cartesian kpoints"][ib][ik]
        k_prm = self.kgrid[tp]["cartesian kpoints"][ib_prm][ik_prm]

        if k[0] == k_prm[0] and k[1] == k_prm[1] and k[2] == k_prm[2]:
            return np.array(
                [0.0, 0.0, 0.0])  # self-scattering is not defined;regardless, the returned integrand must be a vector


        return (1 - X) * norm(k_prm) ** 2 * self.s_el_eq(sname, tp, c, T, k, k_prm) \
               * self.G(tp, ib, ik, ib_prm, ik_prm, X) / (self.kgrid[tp]["norm(v)"][ib_prm][ik_prm] / sq3)



    def inel_integrand_X(self, tp, c, T, ib, ik, ib_prm, ik_prm, X, sname=None, g_suffix=""):
        """
        returns the evaluated number (float) of the expression inside the S_o and S_i(g) integrals.
        :param tp (str): "n" or "p" type
        :param c (float): carrier concentration/doping in cm**-3
        :param T:
        :param ib:
        :param ik:
        :param ib_prm:
        :param ik_prm:
        :param X:
        :param alpha:
        :param sname:
        :return:
        """
        k = self.kgrid[tp]["cartesian kpoints"][ib][ik]
        f = self.kgrid[tp]["f"][c][T][ib][ik]
        f_th = self.kgrid[tp]["f_th"][c][T][ib][ik]
        k_prm = self.kgrid[tp]["cartesian kpoints"][ib_prm][ik_prm]

        v_prm = self.kgrid[tp]["velocity"][ib_prm][ik_prm]
        if tp == "n":
            f_prm = self.kgrid[tp]["f"][c][T][ib_prm][ik_prm]
        else:
            f_prm = 1 - self.kgrid[tp]["f"][c][T][ib_prm][ik_prm]

        if k[0] == k_prm[0] and k[1] == k_prm[1] and k[2] == k_prm[2]:
            return np.array(
            [0.0, 0.0, 0.0])  # self-scattering is not defined;regardless, the returned integrand must be a vector
        #fermi = self.egrid["fermi"][c][T]
        fermi = self.fermi_level[c][T]

        # test
        # f = self.f(self.kgrid[tp]["energy"][ib][ik], fermi, T, tp, c, alpha)
        # f_prm = self.f(self.kgrid[tp]["energy"][ib_prm][ik_prm], fermi, T, tp, c, alpha)

        N_POP = 1 / (np.exp(hbar * self.kgrid[tp]["W_POP"][ib][ik] / (k_B * T)) - 1)
        # norm_diff = max(norm(k-k_prm), 1e-10)
        norm_diff = norm(k - k_prm)
        # print norm(k_prm)**2
        # the term norm(k_prm)**2 is wrong in practice as it can be too big and originally we integrate |k'| from 0
        integ = self.kgrid[tp]["norm(k)"][ib_prm][ik_prm]**2*self.G(tp, ib, ik, ib_prm, ik_prm, X)/\
                (self.kgrid[tp]["norm(v)"][ib_prm][ik_prm]*norm_diff**2)



        if "S_i" in sname:
            integ *= abs(X * self.kgrid[tp]["g" + g_suffix][c][T][ib][ik])
            # integ *= X*self.kgrid[tp]["g" + g_suffix][c][T][ib][ik][alpha]
            if "minus" in sname:
                if tp == "p" or (tp == "n" and \
                    self.kgrid[tp]["energy"][ib][ik]-hbar*self.kgrid[tp]["W_POP"][ib][ik]>=self.cbm_vbm[tp]["energy"]):
                    integ *= (1 - f) * N_POP + f * (1 + N_POP)
            elif "plus" in sname:
                if tp == "n" or (tp == "p" and \
                    self.kgrid[tp]["energy"][ib][ik]+hbar*self.kgrid[tp]["W_POP"][ib][ik]<=self.cbm_vbm[tp]["energy"]):
                    integ *= (1 - f) * (1 + N_POP) + f * N_POP
            else:
                raise ValueError('"plus" or "minus" must be in sname for phonon absorption and emission respectively')
        elif "S_o" in sname:
            if "minus" in sname:
                if tp == "p" or (tp=="n" and \
                    self.kgrid[tp]["energy"][ib][ik]-hbar*self.kgrid[tp]["W_POP"][ib][ik]>=self.cbm_vbm[tp]["energy"]):
                    integ *= (1 - f_prm) * (1 + N_POP) + f_prm * N_POP
            elif "plus" in sname:
                if tp == "n" or (tp == "p" and \
                    self.kgrid[tp]["energy"][ib][ik]+hbar*self.kgrid[tp]["W_POP"][ib][ik]<=self.cbm_vbm[tp]["energy"]):
                    integ *= (1 - f_prm) * N_POP + f_prm * (1 + N_POP)
            else:
                raise ValueError('"plus" or "minus" must be in sname for phonon absorption and emission respectively')
        else:
            raise ValueError("The inelastic scattering name: {} is NOT supported".format(sname))
        return integ



    def s_inel_eq_isotropic(self, once_called=False):
        for tp in ["n", "p"]:
            for c in self.dopings:
                for T in self.temperatures:
                    for ib in range(len(self.kgrid[tp]["energy"])):
                        # only when very large # of k-points are present, make sense to parallelize as this function
                        # has become fast after better energy window selection
                        if self.parallel and len(self.kgrid[tp]["size"]) * max(self.kgrid[tp]["size"]) > 100000:
                            # if False:
                            results = Parallel(n_jobs=self.num_cores)(delayed(calculate_Sio) \
                                                                          (tp, c, T, ib, ik, once_called, self.kgrid,
                                                                           self.cbm_vbm, self.epsilon_s,
                                                                           self.epsilon_inf
                                                                           ) for ik in
                                                                      range(len(self.kgrid[tp]["kpoints"][ib])))
                        else:
                            results = [calculate_Sio(tp, c, T, ib, ik, once_called, self.kgrid, self.cbm_vbm,
                                                     self.epsilon_s, self.epsilon_inf) for ik in
                                       range(len(self.kgrid[tp]["kpoints"][ib]))]

                        for ik, res in enumerate(results):
                            self.kgrid[tp]["S_i"][c][T][ib][ik] = res[0]
                            self.kgrid[tp]["S_i_th"][c][T][ib][ik] = res[1]
                            if not once_called:
                                self.kgrid[tp]["S_o"][c][T][ib][ik] = res[2]
                                self.kgrid[tp]["S_o_th"][c][T][ib][ik] = res[3]



    def s_inelastic(self, sname=None, g_suffix=""):
        for tp in ["n", "p"]:
            for c in self.dopings:
                for T in self.temperatures:
                    for ib in range(len(self.kgrid[tp]["energy"])):
                        for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                            summation = np.array([0.0, 0.0, 0.0])
                            for X_E_index_name in ["X_Eplus_ik", "X_Eminus_ik"]:
                                summation += self.integrate_over_X(tp, self.kgrid[tp][X_E_index_name],
                                                                   self.inel_integrand_X,
                                                                   ib=ib, ik=ik, c=c, T=T, sname=sname + X_E_index_name,
                                                                   g_suffix=g_suffix)
                            # self.kgrid[tp][sname][c][T][ib][ik] = abs(summation) * e**2*self.kgrid[tp]["W_POP"][ib][ik]/(4*pi*hbar) \
                            self.kgrid[tp][sname][c][T][ib][ik] = summation * e ** 2 * self.kgrid[tp]["W_POP"][ib][ik] \
                                                                  / (4 * pi * hbar) * (
                                                                  1 / self.epsilon_inf - 1 / self.epsilon_s) / epsilon_0 * 100 / e
                            # if norm(self.kgrid[tp][sname][c][T][ib][ik]) < 1:
                            #     self.kgrid[tp][sname][c][T][ib][ik] = [1, 1, 1]
                            # if norm(self.kgrid[tp][sname][c][T][ib][ik]) > 1e5:
                            #     print tp, c, T, ik, ib, summation, self.kgrid[tp][sname][c][T][ib][ik]



    def s_el_eq_isotropic(self, sname, tp, c, T, ib, ik):
        """returns elastic scattering rate (a numpy vector) at certain point (e.g. k-point, T, etc)
        with the assumption that the band structure is isotropic (i.e. self.bs_is_isotropic==True).
        This assumption significantly simplifies the model and the integrated rates at each
        k/energy directly extracted from the literature can be used here."""

        v = self.kgrid[tp]["norm(v)"][ib][ik] / sq3  # because of isotropic assumption, we treat the BS as 1D
        # v = self.kgrid[tp]["velocity"][ib][ik] # because it's isotropic, it doesn't matter which one we choose
        # perhaps more correct way of defining knrm is as follows since at momentum is supposed to be proportional to
        # velocity as it is in free-electron formulation so we replaced hbar*knrm with m_e*v/(1e11*e) (momentum)


        # if self.poly_bands: # the first one should be v and NOT v * sq3 so that the two match in SPB
        # if False:  # I'm 90% sure that there is not need for the first type of knrm and that's why I added if False for now
        #     knrm = m_e * self._avg_eff_mass[tp] * (v) / (
        #     hbar * e * 1e11)  # in nm given that v is in cm/s and hbar in eV.s; this resulted in very high ACD and IMP scattering rates, actually only PIE would match with aMoBT results as it doesn't have k_nrm in its formula
        ##TODO: make sure that ACD scattering as well as others match in SPB between bs_is_isotropic and when knrm is the following and not above (i.e. not m*v/hbar*e)
        # else:
        knrm = self.kgrid[tp]["norm(k)"][ib][ik]
        par_c = self.kgrid[tp]["c"][ib][ik]

        if sname.upper() == "ACD":
            # The following two lines are from Rode's chapter (page 38)
            return (k_B * T * self.E_D[tp] ** 2 * knrm ** 2) / (3 * pi * hbar ** 2 * self.C_el * 1e9 * v) \
                   * (3 - 8 * par_c ** 2 + 6 * par_c ** 4) * e * 1e20

            # return (k_B * T * self.E_D[tp] ** 2 * knrm ** 2) *norm(1.0/v)/ (3 * pi * hbar ** 2 * self.C_el * 1e9) \
            #     * (3 - 8 * self.kgrid[tp]["c"][ib][ik] ** 2 + 6 * self.kgrid[tp]["c"][ib][ik] ** 4) * e * 1e20

            # it is equivalent to the following also from Rode but always isotropic
            # return m_e * knrm * self.E_D[tp] ** 2 * k_B * T / ( 3* pi * hbar ** 3 * self.C_el) \
            #            * (3 - 8 * par_c ** 2 + 6 * par_c ** 4) * 1  # units work out! that's why conversion is 1


            # The following is from Deformation potentials and... Ref. [Q] (DOI: 10.1103/PhysRev.80.72 ) page 82?
            # if knrm < 1/(0.1*self._vrun.lattice.c*A_to_nm):

            # replaced hbar*knrm with m_e*norm(v)/(1e11*e) which is momentum
            # return m_e * m_e*v * self.E_D[tp] ** 2 * k_B * T / (3 * pi * hbar ** 4 * self.C_el) \
            #        * (3 - 8 * par_c ** 2 + 6 * par_c ** 4) / (1e11*e) # 1/1e11*e is to convert kg.cm/s to hbar.k units (i.e. ev.s/nm)

        elif sname.upper() == "IMP":  # double-checked the units and equation on 5/12/2017
            # The following is a variation of Dingle's theory available in [R]
            beta = self.egrid["beta"][c][T][tp]
            B_II = (4 * knrm ** 2 / beta ** 2) / (1 + 4 * knrm ** 2 / beta ** 2) + 8 * (beta ** 2 + 2 * knrm ** 2) / (
            beta ** 2 + 4 * knrm ** 2) * par_c ** 2 + \
                   (3 * beta ** 4 + 6 * beta ** 2 * knrm ** 2 - 8 * knrm ** 4) / (
                   (beta ** 2 + 4 * knrm ** 2) * knrm ** 2) * par_c ** 4
            D_II = 1 + 2 * beta ** 2 * par_c ** 2 / knrm ** 2 + 3 * beta ** 4 * par_c ** 4 / (4 * knrm ** 4)

            return abs((e ** 4 * abs(self.egrid["N_II"][c][T])) / (
                8 * pi * v * self.epsilon_s ** 2 * epsilon_0 ** 2 * hbar ** 2 *
                knrm ** 2) * (D_II * log(1 + 4 * knrm ** 2 / beta ** 2) - B_II) * 3.89564386e27)



        elif sname.upper() == "PIE":
            return (e ** 2 * k_B * T * self.P_PIE ** 2) / (
                6 * pi * hbar ** 2 * self.epsilon_s * epsilon_0 * v) * (
                       3 - 6 * par_c ** 2 + 4 * par_c ** 4) * 100 / e

        elif sname.upper() == "DIS":
            return (self.N_dis * e ** 4 * knrm) / (
            hbar ** 2 * epsilon_0 ** 2 * self.epsilon_s ** 2 * (self._vrun.lattice.c * A_to_nm) ** 2 * v) \
                   / (self.egrid["beta"][c][T][tp] ** 4 * (
            1 + (4 * knrm ** 2) / (self.egrid["beta"][c][T][tp] ** 2)) ** 1.5) \
                   * 2.43146974985767e42 * 1.60217657 / 1e8;

        else:
            raise ValueError('The elastic scattering name "{}" is NOT supported.'.format(sname))



    def s_elastic(self, sname):
        """
        the scattering rate equation for each elastic scattering name is entered in s_func and returned the integrated
        scattering rate.
        :param sname (st): the name of the tp of elastic scattering, options are 'IMP', 'ADE', 'PIE', 'POP', 'DIS'
        :param s_func:
        :return:
        """
        sname = sname.upper()

        for tp in ["n", "p"]:
            self.egrid[tp][sname] = {c: {T: np.array([[0.0, 0.0, 0.0] for i in
                                                      range(len(self.egrid[tp]["energy"]))]) for T in
                                         self.temperatures} for c in self.dopings}
            self.kgrid[tp][sname] = {
            c: {T: np.array([[[0.0, 0.0, 0.0] for i in range(len(self.kgrid[tp]["kpoints"][j]))]
                             for j in range(self.cbm_vbm[tp]["included"])]) for T in self.temperatures} for c in
            self.dopings}
            for c in self.dopings:
                for T in self.temperatures:
                    for ib in range(len(self.kgrid[tp]["energy"])):
                        for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                            if self.bs_is_isotropic:
                                self.kgrid[tp][sname][c][T][ib][ik] = self.s_el_eq_isotropic(sname, tp, c, T, ib, ik)
                            else:
                                summation = self.integrate_over_X(tp, X_E_index=self.kgrid[tp]["X_E_ik"],
                                                                  integrand=self.el_integrand_X,
                                                                  ib=ib, ik=ik, c=c, T=T, sname=sname, g_suffix="")
                                self.kgrid[tp][sname][c][T][ib][ik] = abs(summation) * 2e-7 * pi / hbar
                                if norm(self.kgrid[tp][sname][c][T][ib][ik]) < 100 and sname not in ["DIS"]:
                                    print "WARNING!!! here scattering {} < 1".format(sname)
                                    # if self.kgrid[tp]["df0dk"][c][T][ib][ik][0] > 1e-32:
                                    #     print self.kgrid[tp]["df0dk"][c][T][ib][ik]
                                    print self.kgrid[tp]["X_E_ik"][ib][ik]

                                    self.kgrid[tp][sname][c][T][ib][ik] = [1e10, 1e10, 1e10]

                                if norm(self.kgrid[tp][sname][c][T][ib][ik]) > 1e20:
                                    print "WARNING!!! TOO LARGE of scattering rate for {}:".format(sname)
                                    print summation
                                    print self.kgrid[tp]["X_E_ik"][ib][ik]
                                    print
                            self.kgrid[tp]["_all_elastic"][c][T][ib][ik] += self.kgrid[tp][sname][c][T][ib][ik]

                        # logging.debug("relaxation time at c={} and T= {}: \n {}".format(c, T, self.kgrid[tp]["relaxation time"][c][T][ib]))
                        # logging.debug("_all_elastic c={} and T= {}: \n {}".format(c, T, self.kgrid[tp]["_all_elastic"][c][T][ib]))
                        self.kgrid[tp]["relaxation time"][c][T][ib] = 1 / self.kgrid[tp]["_all_elastic"][c][T][ib]



    def map_to_egrid(self, prop_name, c_and_T_idx=True, prop_type="vector"):
        """
        maps a propery from kgrid to egrid conserving the nomenclature. The mapped property should have the
            kgrid[tp][prop_name][c][T][ib][ik] data structure and will have egrid[tp][prop_name][c][T][ie] structure
        :param prop_name (string): the name of the property to be mapped. It must be available in the kgrid.
        :param c_and_T_idx (bool): if True, the propetry will be calculated and maped at each concentration, c, and T
        :param prop_type (str): options are "scalar", "vector", "tensor"
        :return:
        """
        # scalar_properties = ["g"]
        if not c_and_T_idx:
            self.initialize_var("egrid", prop_name, prop_type, initval=self.gs, is_nparray=True, c_T_idx=False)
            for tp in ["n", "p"]:

                if not self.gaussian_broadening:
                    for ie, en in enumerate(self.egrid[tp]["energy"]):
                        first_ib = self.kgrid_to_egrid_idx[tp][ie][0][0]
                        first_ik = self.kgrid_to_egrid_idx[tp][ie][0][1]
                        for ib, ik in self.kgrid_to_egrid_idx[tp][ie]:
                            # if norm(self.kgrid[tp][prop_name][ib][ik]) / norm(self.kgrid[tp][prop_name][first_ib][first_ik]) > 1.25 or norm(self.kgrid[tp][prop_name][ib][ik]) / norm(self.kgrid[tp][prop_name][first_ib][first_ik]) < 0.8:
                            #     logging.debug('ERROR! Some {} values are more than 25% different at k points with the same energy.'.format(prop_name))
                            #     print('first k: {}, current k: {}'.format(norm(self.kgrid[tp][prop_name][first_ib][first_ik]), norm(self.kgrid[tp][prop_name][ib][ik])))
                            #     print('current energy, first energy, ik, first_ik')
                            #     print(self.kgrid[tp]['energy'][ib][ik], self.kgrid[tp]['energy'][first_ib][first_ik], ik, first_ik)
                            if self.bs_is_isotropic and prop_type == "vector":
                                self.egrid[tp][prop_name][ie] += norm(self.kgrid[tp][prop_name][ib][ik]) / sq3
                            else:
                                self.egrid[tp][prop_name][ie] += self.kgrid[tp][prop_name][ib][ik]
                        self.egrid[tp][prop_name][ie] /= len(self.kgrid_to_egrid_idx[tp][ie])

                        # if self.bs_is_isotropic and prop_type=="vector":
                        #     self.egrid[tp][prop_name][ie]=np.array([norm(self.egrid[tp][prop_name][ie])/sq3 for i in range(3)])


                else:
                    raise ValueError(
                        "Guassian Broadening is NOT well tested and abandanded at the begining due to inaccurate results")
                    # for ie, en in enumerate(self.egrid[tp]["energy"]):
                    #     N = 0.0  # total number of instances with the same energy
                    #     for ib in range(self.cbm_vbm[tp]["included"]):
                    #         for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                    #             self.egrid[tp][prop_name][ie] += self.kgrid[tp][prop_name][ib][ik] * \
                    #                 GB(self.kgrid[tp]["energy"][ib][ik]-self.egrid[tp]["energy"][ie], 0.005)
                    #
                    #     self.egrid[tp][prop_name][ie] /= self.cbm_vbm[tp]["included"] * len(self.kgrid[tp]["kpoints"][0])
                    #
                    #     if self.bs_is_isotropic and prop_type=="vector":
                    #         self.egrid[tp][prop_name][ie]=np.array([norm(self.egrid[tp][prop_name][ie])/sq3 for i in range(3)])


        else:
            self.initialize_var("egrid", prop_name, prop_type, initval=self.gs, is_nparray=True, c_T_idx=True)

            for tp in ["n", "p"]:

                if not self.gaussian_broadening:

                    for c in self.dopings:
                        for T in self.temperatures:
                            for ie, en in enumerate(self.egrid[tp]["energy"]):
                                first_ib = self.kgrid_to_egrid_idx[tp][ie][0][0]
                                first_ik = self.kgrid_to_egrid_idx[tp][ie][0][1]
                                for ib, ik in self.kgrid_to_egrid_idx[tp][ie]:
                                    # if norm(self.kgrid[tp][prop_name][c][T][ib][ik]) / norm(
                                    #         self.kgrid[tp][prop_name][c][T][first_ib][first_ik]) > 1.25 or norm(
                                    #         self.kgrid[tp][prop_name][c][T][ib][ik]) / norm(
                                    #         self.kgrid[tp][prop_name][c][T][first_ib][first_ik]) < 0.8:
                                    #     logging.debug('ERROR! Some {} values are more than 25% different at k points with the same energy.'.format(prop_name))
                                    #     print('first k: {}, current k: {}'.format(
                                    #         norm(self.kgrid[tp][prop_name][c][T][first_ib][first_ik]),
                                    #         norm(self.kgrid[tp][prop_name][c][T][ib][ik])))

                                    if self.bs_is_isotropic and prop_type == "vector":
                                        self.egrid[tp][prop_name][c][T][ie] += norm(
                                            self.kgrid[tp][prop_name][c][T][ib][ik]) / sq3
                                    else:
                                        self.egrid[tp][prop_name][c][T][ie] += self.kgrid[tp][prop_name][c][T][ib][ik]
                                self.egrid[tp][prop_name][c][T][ie] /= len(self.kgrid_to_egrid_idx[tp][ie])

                                # if self.bs_is_isotropic and prop_type == "vector":
                                #     self.egrid[tp][prop_name][c][T][ie] = np.array(
                                #         [norm(self.egrid[tp][prop_name][c][T][ie])/sq3 for i in range(3)])

                            # df0dk must be negative but we used norm for df0dk when isotropic
                            if prop_name in ["df0dk"] and self.bs_is_isotropic:
                                self.egrid[tp][prop_name][c][T] *= -1
                else:
                    raise ValueError(
                        "Guassian Broadening is NOT well tested and abandanded at the begining due to inaccurate results")
                    # for c in self.dopings:
                    #     for T in self.temperatures:
                    #         for ie, en in enumerate(self.egrid[tp]["energy"]):
                    #             N = 0.0 # total number of instances with the same energy
                    #             for ib in range(self.cbm_vbm[tp]["included"]):
                    #                 for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                    #                     self.egrid[tp][prop_name][c][T][ie] += self.kgrid[tp][prop_name][c][T][ib][ik] * \
                    #                            GB(self.kgrid[tp]["energy"][ib][ik] -
                    #                                                         self.egrid[tp]["energy"][ie], 0.005)
                    #             self.egrid[tp][prop_name][c][T][ie] /= self.cbm_vbm[tp]["included"] * len(self.kgrid[tp]["kpoints"][0])
                    #
                    #
                    #             if self.bs_is_isotropic and prop_type == "vector":
                    #                 self.egrid[tp][prop_name][c][T][ie] = np.array(
                    #                     [norm(self.egrid[tp][prop_name][c][T][ie])/sq3 for i in range(3)])
                    #
                    #         if prop_name in ["df0dk"]: # df0dk is always negative
                    #             self.egrid[tp][c][T][prop_name] *= -1



    def find_fermi_SPB(self, c, T, tolerance=0.001, tolerance_loose=0.03, alpha=0.02, max_iter=1000):

        tp = self.get_tp(c)
        sgn = np.sign(c)
        m_eff = np.prod(self.cbm_vbm[tp]["eff_mass_xx"]) ** (1.0 / 3.0)
        c *= sgn
        initial_energy = self.cbm_vbm[tp]["energy"]
        fermi = initial_energy + 0.02
        iter = 0
        for iter in range(max_iter):
            calc_doping = 4 * pi * (2 * m_eff * m_e * k_B * T / hbar ** 2) ** 1.5 * fermi_integral(0.5, fermi, T,
                                                                                                   initial_energy) * 1e-6 / e ** 1.5
            fermi += alpha * sgn * (calc_doping - c) / abs(c + calc_doping) * fermi
            relative_error = abs(calc_doping - c) / abs(c)
            if relative_error <= tolerance:
                # This here assumes that the SPB generator set the VBM to 0.0 and CBM=  gap + scissor
                if sgn < 0:
                    return fermi
                else:
                    return -(fermi - initial_energy)
        if relative_error > tolerance:
            raise ValueError("could NOT find a corresponding SPB fermi level after {} itenrations".format(max_iter))




    def find_fermi_k(self, tolerance=0.001):

        closest_energy = {c: {T: None for T in self.temperatures} for c in self.dopings}
        #energy = self.array_from_kgrid('energy', 'n', fill=1000)
        for c in self.dopings:
            tp = self.get_tp(c)
            tol = tolerance * abs(c)
            for T in self.temperatures:
                step = 0.1
                range_of_energies = np.arange(self.cbm_vbm[tp]['energy'] - 2, self.cbm_vbm[tp]['energy'] + 2.1, step)
                diff = 1000 * abs(c)
                while(diff > tol):
                    # try a number for fermi level
                    diffs = {}
                    for e_f in range_of_energies:
                        # calculate distribution
                        f = 1 / (np.exp((self.energy_array[tp] - e_f) / (k_B * T)) + 1)
                        # see if it is close to concentration
                        if tp == 'n':
                            diffs[e_f] = abs(self.integrate_over_states(f)[0] - abs(c))
                        if tp == 'p':
                            diffs[e_f] = abs(self.integrate_over_states(1 - f)[0] - abs(c))
                    # compare all the numbers and zoom in on the closest
                    closest_energy[c][T] = min(diffs, key=diffs.get)
                    range_of_energies = np.arange(closest_energy[c][T] - step, closest_energy[c][T] + step, step / 10)
                    step /= 10
                    diff = diffs[closest_energy[c][T]]

        return closest_energy



    def find_fermi(self, c, T, tolerance=0.001, tolerance_loose=0.03, alpha=0.05, max_iter=5000):
        """
        To find the Fermi level at a carrier concentration and temperature at kgrid (i.e. band structure, DOS, etc)
        :param c (float): The doping concentration; c < 0 indicate n-tp (i.e. electrons) and c > 0 for p-tp
        :param T (float): The temperature.
        :param tolerance (0<float<1): convergance threshold for relative error
        :param tolerance_loose (0<float<1): maximum relative error allowed between the calculated and input c
        :param alpha (float < 1): the fraction of the linear interpolation towards the actual fermi at each iteration
        :param max_iter (int): after this many iterations the function returns even if it is not converged
        :return:
            The fitted/calculated Fermi level
        """

        # initialize parameters
        relative_error = self.gl
        iter = 0.0
        tune_alpha = 1.0
        temp_doping = {"n": -0.01, "p": +0.01}
        typ = self.get_tp(c)
        typj = ["n", "p"].index(typ)
        fermi = self.cbm_vbm[typ]["energy"] + 0.01 * (-1)**typj # addition is to ensure Fermi is not exactly 0.0
        # fermi = self.egrid[typ]["energy"][0]

        print("calculating the fermi level at temperature: {} K".format(T))
        funcs = [lambda E, fermi0, T: f0(E, fermi0, T), lambda E, fermi0, T: 1 - f0(E, fermi0, T)]
        calc_doping = (-1) ** (typj + 1) / self.volume / (A_to_m * m_to_cm) ** 3 \
                      * abs(self.integrate_over_DOSxE_dE(func=funcs[typj], tp=typ, fermi=fermi, T=T))

        while (relative_error > tolerance) and (iter < max_iter):
            # print iter
            # print calc_doping
            # print fermi
            # print (-1) ** (typj)
            # print
            iter += 1  # to avoid an infinite loop
            if iter / max_iter > 0.5:  # to avoid oscillation we re-adjust alpha at each iteration
                tune_alpha = 1 - iter / max_iter
            # fermi += (-1) ** (typj) * alpha * tune_alpha * (calc_doping - c) / abs(c + calc_doping) * fermi
            fermi += alpha * tune_alpha * (calc_doping - c) / abs(c + calc_doping) * abs(fermi)
            if abs(fermi) < 1e-5: # switch sign when getting really close to 0 as otherwise will never converge
                fermi = fermi * -1

            for j, tp in enumerate(["n", "p"]):
                integral = 0.0

                # for ie in range((1 - j) * self.cbm_dos_idx + j * 0,
                #                 (1 - j) * len(self.dos) - 1 + j * self.vbm_dos_idx - 1):
                for ie in range((1 - j) * self.cbm_dos_idx,
                                    (1 - j) * len(self.dos) + j * self.vbm_dos_idx - 1):
                    integral += (self.dos[ie + 1][1] + self.dos[ie][1]) / 2 * funcs[j](self.dos[ie][0], fermi, T) * \
                                (self.dos[ie + 1][0] - self.dos[ie][0])
                temp_doping[tp] = (-1) ** (j + 1) * abs(integral / (self.volume * (A_to_m * m_to_cm) ** 3))

            calc_doping = temp_doping["n"] + temp_doping["p"]
            if abs(calc_doping) < 1e-2:
                calc_doping = np.sign(calc_doping) * 0.01  # just so that calc_doping doesn't get stuck to zero!

            # calculate the relative error from the desired concentration, c
            relative_error = abs(calc_doping - c) / abs(c)

        self.egrid["calc_doping"][c][T]["n"] = temp_doping["n"]
        self.egrid["calc_doping"][c][T]["p"] = temp_doping["p"]

        # check to see if the calculated concentration is close enough to the desired value
        if relative_error > tolerance and relative_error <= tolerance_loose:
            warnings.warn("The calculated concentration {} is not accurate compared to {}; results may be unreliable"
                          .format(calc_doping, c))
        elif relative_error > tolerance_loose:
            raise ValueError("The calculated concentration {} is more than {}% away from {}; "
                             "possible cause may low band gap, high temperature, small nsteps, etc; AMSET stops now!"
                             .format(calc_doping, tolerance_loose * 100, c))

        logging.info("fermi at {} 1/cm3 and {} K after {} iterations: {}".format(c, T, int(iter), fermi))
        return fermi



    def inverse_screening_length(self, c, T):
        """
        calculates the inverse screening length (beta) in 1/nm units
        :param tp:
        :param fermi:
        :param T:
        :param interpolation_nsteps:
        :return:
        """
        beta = {}
        for tp in ["n", "p"]:
            # TODO: the integration may need to be revised. Careful testing of IMP scattering against expt is necessary
            # integral = self.integrate_over_E(func=func, tp=tp, fermi=self.egrid["fermi"][c][T], T=T)

            # because this integral has no denominator to cancel the effect of weights, we do non-weighted integral
            # integrate in egrid with /volume and proper unit conversion
            # we assume here that DOS is normalized already
            # integral = self.integrate_over_E(prop_list=["f0x1-f0"], tp=tp, c=c, T=T, xDOS=True, weighted=False)
            integral = self.integrate_over_normk(prop_list=["f0","1-f0"], tp=tp, c=c, T=T, xDOS=True)
            integral = sum(integral)/3

            # integral = sum(self.integrate_over_BZ(["f0", "1-f0"], tp, c, T, xDOS=False, xvel=False, weighted=False))/3

            # from aMoBT ( or basically integrate_over_normk )
            beta[tp] = (e**2 / (self.epsilon_s * epsilon_0*k_B*T) * integral * 6.241509324e27)**0.5

            # for integrate_over_E
            # beta[tp] = (e ** 2 / (self.epsilon_s * epsilon_0 * k_B * T) * integral / self.volume * 1e12 / e) ** 0.5

            # for integrate_over_BZ: incorrect (tested on 7/18/2017)
            # beta[tp] = (e**2 / (self.epsilon_s * epsilon_0*k_B*T) * integral * 100/e)**0.5

        return beta



    def to_json(self, kgrid=True, trimmed=False, max_ndata=None, nstart=0):

        if not max_ndata:
            max_ndata = int(self.gl)

        egrid = deepcopy(self.egrid)
        if trimmed:
            nmax = min([max_ndata + 1, min([len(egrid["n"]["energy"]), len(egrid["p"]["energy"])])])

            for tp in ["n", "p"]:
                for key in egrid[tp]:
                    if key in ["size"]:
                        continue
                    try:
                        for c in self.dopings:
                            for T in self.temperatures:
                                if tp == "n":
                                    egrid[tp][key][c][T] = self.egrid[tp][key][c][T][nstart:nstart + nmax]
                                else:
                                    egrid[tp][key][c][T] = self.egrid[tp][key][c][T][::-1][nstart:nstart + nmax]
                                    # egrid[tp][key][c][T] = self.egrid[tp][key][c][T][-(nstart+nmax):-max(nstart,1)][::-1]
                    except:
                        try:
                            if tp == "n":
                                egrid[tp][key] = self.egrid[tp][key][nstart:nstart + nmax]
                            else:
                                egrid[tp][key] = self.egrid[tp][key][::-1][nstart:nstart + nmax]
                                # egrid[tp][key] = self.egrid[tp][key][-(nstart+nmax):-max(nstart,1)][::-1]
                        except:
                            print "cutting data for {} numbers in egrid was NOT successful!".format(key)
                            pass

        with open("egrid.json", 'w') as fp:
            json.dump(egrid, fp, sort_keys=True, indent=4, ensure_ascii=False, cls=MontyEncoder)

        # self.kgrid trimming
        if kgrid:
            start_time = time.time()
            kgrid = deepcopy(self.kgrid)
            print "time to copy kgrid = {} seconds".format(time.time() - start_time)
            if trimmed:
                nmax = min([max_ndata + 1, min([len(kgrid["n"]["kpoints"][0]), len(kgrid["p"]["kpoints"][0])])])
                for tp in ["n", "p"]:
                    for key in kgrid[tp]:
                        if key in ["size"]:
                            continue
                        try:
                            for c in self.dopings:
                                for T in self.temperatures:
                                    if tp == "n":
                                        kgrid[tp][key][c][T] = [self.kgrid[tp][key][c][T][b][nstart:nstart + nmax]
                                                            for b in range(self.cbm_vbm[tp]["included"])]
                                    else:
                                        kgrid[tp][key][c][T] = [self.kgrid[tp][key][c][T][b][::-1][nstart:nstart + nmax]
                                                                for b in range(self.cbm_vbm[tp]["included"])]
                                        # kgrid[tp][key][c][T] = [self.kgrid[tp][key][c][T][b][-(nstart+nmax):-max(nstart,1)][::-1]
                                        #                         for b in range(self.cbm_vbm[tp]["included"])]
                        except:
                            try:
                                if tp == "n":
                                    kgrid[tp][key] = [self.kgrid[tp][key][b][nstart:nstart + nmax]
                                                  for b in range(self.cbm_vbm[tp]["included"])]
                                else:
                                    kgrid[tp][key] = [self.kgrid[tp][key][b][::-1][nstart:nstart + nmax]
                                                      for b in range(self.cbm_vbm[tp]["included"])]
                                    # kgrid[tp][key] = [self.kgrid[tp][key][b][-(nstart+nmax):-max(nstart,1)][::-1]
                                    #                   for b in range(self.cbm_vbm[tp]["included"])]
                            except:
                                print "cutting data for {} numbers in kgrid was NOT successful!".format(key)
                                pass

            with open("kgrid.json", 'w') as fp:
                json.dump(kgrid, fp, sort_keys=True, indent=4, ensure_ascii=False, cls=MontyEncoder)



    # def solve_BTE_anisotropic(self):
        # do some solving
        # find the coefficients due to scattering
        # add in the coefficients due to finite difference derivatives
        # solve the linear system



    def solve_BTE_iteratively(self):
        # calculating S_o scattering rate which is not a function of g
        if "POP" in self.inelastic_scatterings and not self.bs_is_isotropic:
            for g_suffix in ["", "_th"]:
                self.s_inelastic(sname="S_o" + g_suffix, g_suffix=g_suffix)

        # solve BTE to calculate S_i scattering rate and perturbation (g) in an iterative manner
        for iter in range(self.BTE_iters):
            print("Performing iteration # {}".format(iter))

            if "POP" in self.inelastic_scatterings:
                if self.bs_is_isotropic:
                    if iter == 0:
                        self.s_inel_eq_isotropic(once_called=False)
                    else:
                        self.s_inel_eq_isotropic(once_called=True)

                else:
                    for g_suffix in ["", "_th"]:
                        self.s_inelastic(sname="S_i" + g_suffix, g_suffix=g_suffix)
            for c in self.dopings:
                for T in self.temperatures:
                    for tp in ["n", "p"]:
                        g_old = np.array(self.kgrid[tp]["g"][c][T][0])
                        for ib in range(self.cbm_vbm[tp]["included"]):

                            self.kgrid[tp]["g_POP"][c][T][ib] = (self.kgrid[tp]["S_i"][c][T][ib] +
                                                                 self.kgrid[tp]["electric force"][c][T][ib]) / (
                                                                    self.kgrid[tp]["S_o"][c][T][ib] + self.gs)

                            self.kgrid[tp]["g"][c][T][ib] = (self.kgrid[tp]["S_i"][c][T][ib] +
                                                             self.kgrid[tp]["electric force"][c][
                                                                 T][ib]) / (self.kgrid[tp]["S_o"][c][T][ib] +
                                                                            self.kgrid[tp]["_all_elastic"][c][T][ib])

                            self.kgrid[tp]["g_th"][c][T][ib] = (self.kgrid[tp]["S_i_th"][c][T][ib] +
                                                                self.kgrid[tp]["thermal force"][c][
                                                                    T][ib]) / (self.kgrid[tp]["S_o_th"][c][T][ib] +
                                                                               self.kgrid[tp]["_all_elastic"][c][T][ib])

                            # TODO: correct these lines to reflect that f = f0 + x*g
                            self.kgrid[tp]["f"][c][T][ib] = self.kgrid[tp]["f0"][c][T][ib] + self.kgrid[tp]["g"][c][T][
                                ib]
                            self.kgrid[tp]["f_th"][c][T][ib] = self.kgrid[tp]["f0"][c][T][ib] + \
                                                               self.kgrid[tp]["g_th"][c][T][ib]

                            for ik in range(len(self.kgrid[tp]["kpoints"][ib])):
                                if norm(self.kgrid[tp]["g_POP"][c][T][ib][ik]) > 1 and iter > 0:
                                    # because only when there are no S_o/S_i scattering events, g_POP>>1 while it should be zero
                                    self.kgrid[tp]["g_POP"][c][T][ib][ik] = [self.gs, self.gs, self.gs]

                        avg_g_diff = np.mean(
                            [abs(g_old[ik] - self.kgrid[tp]["g"][c][T][0][ik]) for ik in range(len(g_old))])
                        print("Average difference in {}-type g term at c={} and T={}: {}".format(tp, c, T, avg_g_diff))

        for prop in ["electric force", "thermal force", "g", "g_POP", "g_th", "S_i", "S_o", "S_i_th", "S_o_th"]:
            self.map_to_egrid(prop_name=prop, c_and_T_idx=True)

        # this code has been commented out because egrid is no longer in use, but it might still be necessary in kgrid
        for tp in ["n", "p"]:
            for c in self.dopings:
                for T in self.temperatures:
                    for ie in range(len(self.egrid[tp]["g_POP"][c][T])):
                        if norm(self.egrid[tp]["g_POP"][c][T][ie]) > 1:
                            self.egrid[tp]["g_POP"][c][T][ie] = [1e-5, 1e-5, 1e-5]


    def calc_v_vec(self, tp):
        # TODO: Take into account the fact that this gradient is found in three directions specified by the lattice, not
        # the x, y, and z directions. It must be corrected to account for this.
        energy_grid = self.array_from_kgrid('energy', tp)
        # print('energy:')
        # np.set_printoptions(precision=3)
        # print(energy_grid[0,:,:,:,0])
        N = self.kgrid_array['k_points'].shape
        k_grid = self.kgrid_array['k_points']
        v_vec_result = []
        for ib in range(self.num_bands[tp]):
            v_vec = np.gradient(energy_grid[ib][:,:,:,0], k_grid[:,0,0,0] * self._rec_lattice.a, k_grid[0,:,0,1] * self._rec_lattice.b, k_grid[0,0,:,2] * self._rec_lattice.c)
            v_vec_rearranged = np.zeros((N[0], N[1], N[2], 3))
            for i in range(N[0]):
                for j in range(N[1]):
                    for k in range(N[2]):
                        v_vec_rearranged[i,j,k,:] = np.array([v_vec[0][i,j,k], v_vec[1][i,j,k], v_vec[2][i,j,k]])
            v_vec_rearranged *= A_to_m * m_to_cm / hbar
            v_vec_result.append(v_vec_rearranged)
        return np.array(v_vec_result)


    # turns a kgrid property into a list of grid arrays of that property for k integration
    def array_from_kgrid(self, prop_name, tp, c=None, T=None, denom=False, none_missing=False, fill=None):
        if c:
            return np.array([self.grid_from_energy_list(self.kgrid[tp][prop_name][c][T][ib], tp, ib, denom=denom, none_missing=none_missing, fill=fill) for ib in range(self.num_bands[tp])])
        else:
            return np.array([self.grid_from_energy_list(self.kgrid[tp][prop_name][ib], tp, ib, denom=denom, none_missing=none_missing, fill=fill) for ib in range(self.num_bands[tp])])


    # takes a list that is sorted by energy and missing removed points
    def grid_from_energy_list(self, prop_list, tp, ib, denom=False, none_missing=False, fill=None):

        if not fill:
            if not denom:
                fill = 0
            if denom:
                fill = 1
        adjusted_prop_list = list(prop_list)
        # step 0 is reverse second sort
        adjusted_prop_list = np.array(adjusted_prop_list)[self.pos_idx_2[tp][ib]]
        adjusted_prop_list = [adjusted_prop_list[i] for i in range(adjusted_prop_list.shape[0])]

        # reverse what has been done: step 1 is add new points back
        if not none_missing:
            insert_list = False
            if type(adjusted_prop_list[0]) == np.ndarray or type(adjusted_prop_list[0]) == list:
                if len(adjusted_prop_list[0]) == 3:
                    insert_list = True
            for ib in range(self.num_bands[tp]):
                for ik in self.rm_idx_list[tp][ib]:
                    adjusted_prop_list.insert(ik, fill) if not insert_list else adjusted_prop_list.insert(ik, [fill,fill,fill])

        # step 2 is reorder based on first sort
        adjusted_prop_list = np.array(adjusted_prop_list)[self.pos_idx[tp]]
        # then call grid_from_ordered_list
        return self.grid_from_ordered_list(adjusted_prop_list, tp, denom=denom, none_missing=True)


    # return a grid of the (x,y,z) k points in the proper grid
    def grid_from_ordered_list(self, prop_list, tp=None, denom=False, none_missing=False):
        # need:
        # self.kgrid_array
        N = self.kgrid_array['k_points'].shape
        grid = np.zeros(N)
        adjusted_prop_list = list(prop_list)

        # put zeros back into spots of missing indexes
        # self.rm_idx_list format: [tp][ib][ik]
        if not none_missing:
            for ib in range(self.num_bands[tp]):
                for ik in self.rm_idx_list[tp][ib]:
                    if not denom:
                        adjusted_prop_list.insert(ik, 0)
                    if denom:
                        adjusted_prop_list.insert(ik, 1)

        for i in range(N[0]):
            for j in range(N[1]):
                for k in range(N[2]):
                    grid[i,j,k] = adjusted_prop_list[i*N[1]*N[2] + j*N[2] + k]
        return grid


    # takes list or array of array grids
    def integrate_over_states(self, integrand_grid):

        integrand_grid = np.array(integrand_grid)

        if type(integrand_grid[0][0,0,0]) == list or type(integrand_grid[0][0,0,0]) == np.ndarray:
            result = np.zeros(3)
        else:
            result = 0
        num_bands = integrand_grid.shape[0]

        for ib in range(num_bands):
            result += self.integrate_over_k(integrand_grid[ib])
        return result


    # calculates transport properties for isotropic materials
    def calculate_transport_properties_with_k(self):
        # calculate mobility by averaging velocity per electric field strength
        mu_num = {tp: {el_mech: {c: {T: [0, 0, 0] for T in self.temperatures} for c in self.dopings} for el_mech in self.elastic_scatterings} for tp in ["n", "p"]}
        mu_denom = deepcopy(mu_num)
        mo_labels = self.elastic_scatterings + self.inelastic_scatterings + ['overall', 'average']
        self.mobility = {tp: {el_mech: {c: {T: [0, 0, 0] for T in self.temperatures} for c in self.dopings} for el_mech in mo_labels} for tp in ["n", "p"]}

        #k_hat = np.array([self.k_hat_grid for ib in range(self.num_bands)])
        N = self.kgrid_array['k_points'].shape

        for c in self.dopings:
            for T in self.temperatures:
                for j, tp in enumerate(["p", "n"]):

                    print('tp =  ' + tp + ':')
                    # get quantities that are independent of mechanism
                    num_k = [len(self.kgrid[tp]["energy"][ib]) for ib in range(self.num_bands[tp])]
                    df0dk = self.array_from_kgrid('df0dk', tp, c, T)
                    v = self.array_from_kgrid('velocity', tp)
                    #v = self.calc_v_vec(tp)
                    norm_v = np.array([self.grid_from_energy_list([norm(self.kgrid[tp]["velocity"][ib][ik]) / sq3 for ik in
                                                          range(num_k[ib])], tp, ib) for ib in range(self.num_bands[tp])])
                    #norm_v = grid_norm(v)
                    f0_removed = self.array_from_kgrid('f0', tp, c, T)
                    #energy = self.array_from_kgrid('energy', tp, fill=1000000)
                    #f0 = 1 / (np.exp((energy - self.fermi_level[c][T]) / (k_B * T)) + 1)
                    for ib in range(self.num_bands[tp]):
                        print('energy (type {}, band {}):'.format(tp, ib))
                        print(self.energy_array[tp][ib][(N[0] - 1) / 2, (N[1] - 1) / 2, :])
                    f0_all = 1 / (np.exp((self.energy_array[tp] - self.fermi_level[c][T]) / (k_B * T)) + 1)
                    #f0_all = 1 / (np.exp((self.energy_array[self.get_tp(c)] - self.fermi_level[c][T]) / (k_B * T)) + 1)

                    np.set_printoptions(precision=3)
                    # print('v:')
                    # print(v[0,:3,:3,:3,:])
                    # print('df0dk:')
                    # print(df0dk[0,4,:,:,0])
                    # print(df0dk[0, 4, :, :, 1])
                    # print(df0dk[0, 4, :, :, 2])
                    # print('electric force:')
                    # print(self.kgrid[tp]["electric force"][c][T][0])

                    # TODO: the anisotropic case is not correct right now
                    if not self.bs_is_isotropic:   # this is NOT working

                        # from equation 44 in Rode, overall
                        nu_el = self.array_from_kgrid('_all_elastic', tp, c, T, denom=True)
                        S_i = 0
                        S_o = 1
                        numerator = -self.integrate_over_states(v * self.k_hat_grid * (-1 / hbar) * df0dk / nu_el)
                        denominator = self.integrate_over_states(f0) * hbar * default_small_E
                        self.mobility[tp]['overall'][c][T] = numerator / denominator

                        # from equation 44 in Rode, elastic
                        #el_mech stands for elastic mechanism
                        for el_mech in self.elastic_scatterings:
                            nu_el = self.array_from_kgrid(el_mech, tp, c, T, denom=True)
                            # includes e in numerator because hbar is in eV units, where e = 1
                            numerator = -self.integrate_over_states(v * self.k_hat_grid * df0dk / nu_el)
                            denominator = self.integrate_over_states(f0) * hbar
                            # for ib in range(len(self.kgrid[tp]["energy"])):
                            #     #num_kpts = len(self.kgrid[tp]["energy"][ib])
                            #     # integrate numerator / norm(F) of equation 44 in Rode
                            #     for dim in range(3):
                            #         # TODO: add in f0 to the integral so that this works for anisotropic materials
                            #         mu_num[tp][el_mech][c][T][dim] += self.integrate_over_k(v_vec[ib] * k_hat[ib] * df0dk[ib] / nu_el[ib])[dim]
                            #         mu_denom[tp][el_mech][c][T][dim] += self.integrate_over_k(f0[ib])[dim]

                            # should be -e / hbar but hbar already in eV units, where e=1
                            self.mobility[tp][el_mech][c][T] = numerator / denominator

                        # from equation 44 in Rode, inelastic
                        for inel_mech in self.inelastic_scatterings:
                            nu_el = self.array_from_kgrid('_all_elastic', tp, c, T, denom=True)
                            S_i = 0
                            S_o = 1
                            self.mobility[tp][inel_mech][c][T] = self.integrate_over_states(
                                v * self.k_hat_grid * (-1 / hbar) * df0dk / S_o)

                        if tp == "n":
                            for mech in self.elastic_scatterings + ['overall']:
                                print('new {} mobility at T={}: {}'.format(mech, T, self.mobility[tp][mech][c][T]))

                    if self.bs_is_isotropic:
                        # from equation 45 in Rode, elastic mechanisms
                        for ib in range(self.num_bands[tp]):
                            print('f0 (type {}, band {}):'.format(tp, ib))
                            print(f0_all[ib, (N[0]-1)/2, (N[1]-1)/2, :])
                        if tp == 'n':
                            denominator = 3 * default_small_E * self.integrate_over_states(f0_all)
                        if tp == 'p':
                            denominator = 3 * default_small_E * self.integrate_over_states(1-f0_all)
                        # print('denominator:')
                        # print(denominator)
                        for el_mech in self.elastic_scatterings:
                            nu_el = self.array_from_kgrid(el_mech, tp, c, T, denom=True)
                            # this line should have -e / hbar except that hbar is in units of eV*s so in those units e=1
                            g = -1 / hbar * df0dk / nu_el
                            # print('g*norm(v) for {}:'.format(el_mech))
                            # print((g * norm_v)[0, (N[0]-1)/2, (N[1]-1)/2, :])
                            self.mobility[tp][el_mech][c][T] = self.integrate_over_states(g * norm_v) / denominator

                        # from equation 45 in Rode, inelastic mechanisms
                        for inel_mech in self.inelastic_scatterings:
                            g = self.array_from_kgrid("g_"+inel_mech, tp, c, T)
                            # print('g*norm(v) for {}:'.format(inel_mech))
                            # print((g * norm_v)[0, (N[0]-1)/2, (N[1]-1)/2, :])
                            self.mobility[tp][inel_mech][c][T] = self.integrate_over_states(g * norm_v) / denominator

                        # from equation 45 in Rode, overall
                        g = self.array_from_kgrid("g", tp, c, T)
                        #print('g: {}'.format(g))
                        #print('norm_v: {}'.format(norm_v))
                        for ib in range(self.num_bands[tp]):
                            print('g for overall (type {}, band {}):'.format(tp, ib))
                            print(g[ib, (N[0] - 1) / 2, (N[1] - 1) / 2, :])
                            print('norm(v) for overall (type {}, band {}):'.format(tp, ib))
                            print(norm_v[ib, (N[0] - 1) / 2, (N[1] - 1) / 2, :])
                            print('g*norm(v) for overall (type {}, band {}):'.format(tp, ib))
                            print((g * norm_v)[ib, (N[0]-1)/2, (N[1]-1)/2, :])
                        self.mobility[tp]['overall'][c][T] = self.integrate_over_states(g * norm_v) / denominator

                    print('new {}-type overall mobility at T = {}: {}'.format(tp, T, self.mobility[tp]['overall'][c][T]))
                    for el_mech in self.elastic_scatterings + self.inelastic_scatterings:
                        print('new {}-type {} mobility at T = {}: {}'.format(tp, el_mech, T, self.mobility[tp][el_mech][c][T]))

                    # figure out average mobility
                    faulty_overall_mobility = False
                    mu_overrall_norm = norm(self.mobility[tp]["overall"][c][T])
                    for transport in self.elastic_scatterings + self.inelastic_scatterings:
                        # averaging all mobility values via Matthiessen's rule
                        self.mobility[tp]["average"][c][T] += 1 / (np.array(self.mobility[tp][transport][c][T]) + 1e-50)
                        if mu_overrall_norm > norm(self.mobility[tp][transport][c][T]):
                            faulty_overall_mobility = True  # because the overall mobility should be lower than all
                    self.mobility[tp]["average"][c][T] = 1 / np.array(self.mobility[tp]["average"][c][T])

                    # Decide if the overall mobility make sense or it should be equal to average (e.g. when POP is off)
                    if mu_overrall_norm == 0.0 or faulty_overall_mobility:
                        self.mobility[tp]["overall"][c][T] = self.mobility[tp]["average"][c][T]



    def calculate_transport_properties_with_E(self):
        integrate_over_kgrid = False
        for c in self.dopings:
            for T in self.temperatures:
                for j, tp in enumerate(["p", "n"]):

                    # mobility numerators
                    for mu_el in self.elastic_scatterings:
                        if integrate_over_kgrid:
                            self.egrid["mobility"][mu_el][c][T][tp] = (-1) * default_small_E / hbar * \
                                                                      self.integrate_over_BZ(
                                                                          prop_list=["/" + mu_el, "df0dk"], tp=tp, c=c,
                                                                          T=T, xDOS=False, xvel=True,
                                                                          weighted=True) #* 1e-7 * 1e-3 * self.volume

                        else:
                            self.egrid["mobility"][mu_el][c][T][tp] = (-1) * default_small_E / hbar * \
                                                                      self.integrate_over_E(
                                                                          prop_list=["/" + mu_el, "df0dk"], tp=tp, c=c,
                                                                          T=T, xDOS=False, xvel=True, weighted=True)
                            if tp == "n":
                                print('old {} numerator = {}'.format(mu_el, self.egrid["mobility"][mu_el][c][T][tp]))

                    if integrate_over_kgrid:
                        if tp == "n":
                            denom = self.integrate_over_BZ(["f0"], tp, c, T, xDOS=False, xvel=False,
                                                       weighted=False) #* 1e-7 * 1e-3 * self.volume
                            print('old denominator = ' + str(denom))
                        else:
                            denom = self.integrate_over_BZ(["1 - f0"], tp, c, T, xDOS=False, xvel=False,
                                                           weighted=False)
                    else:
                        if tp == "n":
                            denom = self.integrate_over_E(prop_list=["f0"], tp=tp, c=c, T=T, xDOS=False, xvel=False,
                                                      weighted=False)
                        else:
                            denom = self.integrate_over_E(prop_list=["1 - f0"], tp=tp, c=c, T=T, xDOS=False, xvel=False,
                                                          weighted=False)

                    print "denom for {}-type with integrate_over_kgrid: {}: \n {}".format(tp, integrate_over_kgrid, denom)

                    if integrate_over_kgrid:
                        for mu_inel in self.inelastic_scatterings:
                            self.egrid["mobility"][mu_inel][c][T][tp] = self.integrate_over_BZ(
                                prop_list=["g_" + mu_inel], tp=tp, c=c, T=T, xDOS=False, xvel=True, weighted=True)
                        self.egrid["mobility"]["overall"][c][T][tp] = self.integrate_over_BZ(["g"], tp, c, T,
                                                                                             xDOS=False, xvel=True,
                                                                                             weighted=True)
                        print "overll numerator"
                        print self.egrid["mobility"]["overall"][c][T][tp]
                    else:
                        for mu_inel in self.inelastic_scatterings:
                            # calculate mobility["POP"] based on g_POP
                            self.egrid["mobility"][mu_inel][c][T][tp] = self.integrate_over_E(
                                prop_list=["g_" + mu_inel], tp=tp, c=c, T=T, xDOS=False,xvel=True, weighted=True)

                        self.egrid["mobility"]["overall"][c][T][tp] = self.integrate_over_E(prop_list=["g"],
                                                                                            tp=tp, c=c, T=T, xDOS=False,
                                                                                            xvel=True, weighted=True)

                    self.egrid["J_th"][c][T][tp] = (self.integrate_over_E(prop_list=["g_th"], tp=tp, c=c, T=T,
                                                                          xDOS=False, xvel=True,
                                                                          weighted=True) / denom) * e * abs(
                        c)  # in units of A/cm2

                    for transport in self.elastic_scatterings + self.inelastic_scatterings + ["overall"]:
                        self.egrid["mobility"][transport][c][T][tp] /= 3 * default_small_E * denom

                    # The following did NOT work as J_th only has one integral (see aMoBT but that one is over k)
                    # and with that one the units don't work out and if you use two integral, J_th will be of 1e6 order!
                    # self.egrid["J_th"][c][T][tp] = self.integrate_over_E(prop_list=["g_th"], tp=tp, c=c, T=T,
                    #         xDOS=False, xvel=True, weighted=True) * e * 1e24  # to bring J to A/cm2 units
                    # self.egrid["J_th"][c][T][tp] /= 3*self.volume*self.integrate_over_E(prop_list=["f0"], tp=tp, c=c,
                    #         T=T, xDOS=False, xvel=False, weighted=True)

                    # other semi-empirical mobility values:
                    #fermi = self.egrid["fermi"][c][T]
                    fermi = self.fermi_level[c][T]
                    # fermi_SPB = self.egrid["fermi_SPB"][c][T]
                    energy = self.cbm_vbm[self.get_tp(c)]["energy"]

                    # for mu in ["overall", "average"] + self.inelastic_scatterings + self.elastic_scatterings:
                    #     self.egrid["mobility"][mu][c][T][tp] /= 3.0

                    # ACD mobility based on single parabolic band extracted from Thermoelectric Nanomaterials,
                    # chapter 1, page 12: "Material Design Considerations Based on Thermoelectric Quality Factor"
                    self.egrid["mobility"]["SPB_ACD"][c][T][tp] = 2 ** 0.5 * pi * hbar ** 4 * e * self.C_el * 1e9 / (
                    # C_el in GPa
                        3 * (self.cbm_vbm[tp]["eff_mass_xx"] * m_e) ** 2.5 * (k_B * T) ** 1.5 * self.E_D[tp] ** 2) \
                                                                  * fermi_integral(0, fermi, T, energy, wordy=True) \
                                                                  / fermi_integral(0.5, fermi, T, energy,
                                                                                   wordy=True) * e ** 0.5 * 1e4  # to cm2/V.s

                    faulty_overall_mobility = False
                    mu_overrall_norm = norm(self.egrid["mobility"]["overall"][c][T][tp])
                    for transport in self.elastic_scatterings + self.inelastic_scatterings:
                        # averaging all mobility values via Matthiessen's rule
                        self.egrid["mobility"]["average"][c][T][tp] += 1 / self.egrid["mobility"][transport][c][T][tp]
                        if mu_overrall_norm > norm(self.egrid["mobility"][transport][c][T][tp]):
                            faulty_overall_mobility = True  # because the overall mobility should be lower than all
                    self.egrid["mobility"]["average"][c][T][tp] = 1 / self.egrid["mobility"]["average"][c][T][tp]

                    # Decide if the overall mobility make sense or it should be equal to average (e.g. when POP is off)
                    if mu_overrall_norm == 0.0 or faulty_overall_mobility:
                        self.egrid["mobility"]["overall"][c][T][tp] = self.egrid["mobility"]["average"][c][T][tp]

                    self.egrid["relaxation time constant"][c][T][tp] = self.egrid["mobility"]["overall"][c][T][tp] \
                                                                       * 1e-4 * m_e * self.cbm_vbm[tp][
                                                                           "eff_mass_xx"] / e  # 1e-4 to convert cm2/V.s to m2/V.s

                    print('old {}-type overall mobility at T = {}: {}'.format(tp, T, self.egrid["mobility"]["overall"][c][T][tp]))
                    for mech in self.elastic_scatterings + self.inelastic_scatterings:
                        print('old {}-type {} mobility at T = {}: {}'.format(tp, mech, T, self.egrid["mobility"][mech][c][T][tp]))

                    # calculating other overall transport properties:
                    self.egrid["conductivity"][c][T][tp] = self.egrid["mobility"]["overall"][c][T][tp] * e * abs(c)
                    # self.egrid["seebeck"][c][T][tp] = -1e6 * k_B * (self.egrid["Seebeck_integral_numerator"][c][T][tp] \
                    #                                                 / self.egrid["Seebeck_integral_denominator"][c][T][
                    #                                                     tp] - (
                    #                                                 self.egrid["fermi"][c][T] - self.cbm_vbm[tp][
                    #                                                     "energy"]) / (k_B * T))
                    self.egrid["seebeck"][c][T][tp] = -1e6 * k_B * (self.egrid["Seebeck_integral_numerator"][c][T][tp] \
                                                                    / self.egrid["Seebeck_integral_denominator"][c][T][
                                                                        tp] - (
                                                                        self.fermi_level[c][T] - self.cbm_vbm[tp][
                                                                            "energy"]) / (k_B * T))
                    self.egrid["TE_power_factor"][c][T][tp] = self.egrid["seebeck"][c][T][tp] ** 2 \
                                                              * self.egrid["conductivity"][c][T][tp] / 1e6  # in uW/cm2K
                    if "POP" in self.inelastic_scatterings:  # when POP is not available J_th is unreliable
                        self.egrid["seebeck"][c][T][tp] = np.array([self.egrid["seebeck"][c][T][tp] for i in range(3)])
                        self.egrid["seebeck"][c][T][tp] += 0.0
                        # TODO: for now, we ignore the following until we figure out the units see why values are high!
                        # self.egrid["seebeck"][c][T][tp] += 1e6 \
                        #                 * self.egrid["J_th"][c][T][tp]/self.egrid["conductivity"][c][T][tp]/dTdz

                    print "3 {}-seebeck terms at c={} and T={}:".format(tp, c, T)
                    print self.egrid["Seebeck_integral_numerator"][c][T][tp] \
                          / self.egrid["Seebeck_integral_denominator"][c][T][tp] * -1e6 * k_B
                    #print + (self.egrid["fermi"][c][T] - self.cbm_vbm[tp]["energy"]) * 1e6 * k_B / (k_B * T)
                    print + (self.fermi_level[c][T] - self.cbm_vbm[tp]["energy"]) * 1e6 * k_B / (k_B * T)
                    print + self.egrid["J_th"][c][T][tp] / self.egrid["conductivity"][c][T][tp] / dTdz * 1e6


                    #TODO: not sure about the following part yet specially as sometimes due to position of fermi I get very off other type mobility values! (sometimes very large)
                    other_type = ["p", "n"][1 - j]
                    self.egrid["seebeck"][c][T][tp] = (self.egrid["conductivity"][c][T][tp] * \
                                                       self.egrid["seebeck"][c][T][tp] -
                                                       self.egrid["conductivity"][c][T][other_type] * \
                                                       self.egrid["seebeck"][c][T][other_type]) / (
                                                      self.egrid["conductivity"][c][T][tp] +
                                                      self.egrid["conductivity"][c][T][other_type])
                    ## since sigma = c_e x e x mobility_e + c_h x e x mobility_h:
                    ## self.egrid["conductivity"][c][T][tp] += self.egrid["conductivity"][c][T][other_type]



    # for plotting
    def get_scalar_output(self, vec, dir):
        if dir == 'x':
            return vec[0]
        if dir == 'y':
            return vec[1]
        if dir == 'z':
            return vec[2]
        if dir == 'avg':
            return sum(vec) / 3



    def create_plots(self, x_label, y_label, show_interactive, save_format, c, tp, file_suffix,
                     textsize, ticksize, path, margin_left, margin_bottom, fontfamily, x_data=None, y_data=None,
                     all_plots=None, x_label_short='', y_label_short=None, y_axis_type='linear', plot_title=None):
        from matminer.figrecipes.plotly.make_plots import PlotlyFig
        if not plot_title:
            plot_title = '{} for {}, c={}'.format(y_label, self.tp_title[tp], c)
        if not y_label_short:
            y_label_short = y_label
        if show_interactive:
            if not x_label_short:
                filename = os.path.join(path, "{}_{}.{}".format(y_label_short, file_suffix, 'html'))
            else:
                filename = os.path.join(path, "{}_{}_{}.{}".format(y_label_short, x_label_short, file_suffix, 'html'))
            plt = PlotlyFig(x_title=x_label, y_title=y_label,
                            plot_title=plot_title, textsize=textsize,
                            plot_mode='offline', filename=filename, ticksize=ticksize,
                            margin_left=margin_left, margin_bottom=margin_bottom, fontfamily=fontfamily)
            if all_plots:
                plt.xy_plot(x_col=[], y_col=[], add_xy_plot=all_plots, y_axis_type=y_axis_type, color='black', showlegend=True)
            else:
                plt.xy_plot(x_col=x_data, y_col=y_data, y_axis_type=y_axis_type, color='black')
        if save_format is not None:
            if not x_label_short:
                filename = os.path.join(path, "{}_{}.{}".format(y_label_short, file_suffix, save_format))
            else:
                filename = os.path.join(path, "{}_{}_{}.{}".format(y_label_short, x_label_short, file_suffix, save_format))
            plt = PlotlyFig(x_title=x_label, y_title=y_label,
                            plot_title=plot_title, textsize=textsize,
                            plot_mode='static', filename=filename, ticksize=ticksize,
                            margin_left=margin_left, margin_bottom=margin_bottom, fontfamily=fontfamily)
            if all_plots:
                plt.xy_plot(x_col=[], y_col=[], add_xy_plot=all_plots, y_axis_type=y_axis_type, color='black', showlegend=True)
            else:
                plt.xy_plot(x_col=x_data, y_col=y_data, y_axis_type=y_axis_type, color='black')



    def plot(self, k_plots=[], E_plots=[], mobility=True, concentrations='all', carrier_types=['n', 'p'],
             direction=['avg'], show_interactive=True, save_format='png', textsize=40, ticksize=30, path=None,
             margin_left=160, margin_bottom=120, fontfamily="serif"):
        """
        plots the calculated values
        :param k_plots: (list of strings) the names of the quantities to be plotted against norm(k)
            options: 'energy', 'df0dk', 'velocity', or just string 'all' (not in a list) to plot everything
        :param E_plots: (list of strings) the names of the quantities to be plotted against E
            options: 'frequency', 'relaxation time', '_all_elastic', 'df0dk', 'velocity', 'ACD', 'IMP', 'PIE', 'g',
            'g_POP', 'g_th', 'S_i', 'S_o', or just string 'all' (not in a list) to plot everything
        :param mobility: (boolean) if True, create a mobility against temperature plot
        :param concentrations: (list of strings) a list of carrier concentrations, or the string 'all' to plot the
            results of calculations done with all input concentrations
        :param carrier_types: (list of strings) select carrier types to plot data for - ['n'], ['p'], or ['n', 'p']
        :param direction: (list of strings) options to include in list are 'x', 'y', 'z', 'avg'; determines which
            components of vector quantities are plotted
        :param show_interactive: (boolean) if True creates and shows interactive html plots
        :param save_format: (str) format for saving plots; options are 'png', 'jpeg', 'svg', 'pdf', None (None does not
            save the plots). NOTE: plotly credentials are needed, see figrecipes documentation
        :param textsize: (int) size of title and axis label text
        :param ticksize: (int) size of axis tick label text
        :param path: (string) location to save plots
        :param margin_left: (int) plotly left margin
        :param margin_bottom: (int) plotly bottom margin
        :param fontfamily: (string) plotly font
        """

        if k_plots == 'all':
            k_plots = ['energy', 'df0dk', 'velocity']
        if E_plots == 'all':
            E_plots = ['frequency', 'relaxation time', 'df0dk', 'velocity'] + self.elastic_scatterings
            if "POP" in self.inelastic_scatterings:
                E_plots += ['g', 'g_POP', 'S_i', 'S_o']

        if concentrations == 'all':
            concentrations = self.dopings

        # make copies of mutable arguments
        k_plots = list(k_plots)
        E_plots = list(E_plots)
        concentrations = list(concentrations)
        carrier_types = list(carrier_types)
        direction = list(direction)

        mu_list = ["overall", "average"] + self.elastic_scatterings + self.inelastic_scatterings
        mu_markers = {mu: i for i, mu in enumerate(mu_list)}
        temp_markers = {T: i for i,T in enumerate(self.temperatures)}

        if not path:
            path = os.path.join(os.getcwd(), "plots")
            if not os.path.exists(path):
                os.makedirs(name=path)

        # separate temperature dependent and independent properties
        all_temp_independent_k_props = ['energy', 'velocity']
        all_temp_independent_E_props = ['frequency', 'velocity']
        temp_independent_k_props = []
        temp_independent_E_props = []
        temp_dependent_k_props = []
        for prop in k_plots:
            if prop in all_temp_independent_k_props:
                temp_independent_k_props.append(prop)
            else:
                temp_dependent_k_props.append(prop)
        temp_dependent_E_props = []
        for prop in E_plots:
            if prop in all_temp_independent_E_props:
                temp_independent_E_props.append(prop)
            else:
                temp_dependent_E_props.append(prop)

        vec = {'energy': False,
               'velocity': True,
               'frequency': False}

        for tp in carrier_types:
            x_data = {'k': self.kgrid[tp]["norm(k)"][0],
                      'E': [E - self.cbm_vbm[tp]["energy"] for E in self.egrid[tp]["energy"]]}
            x_axis_label = {'k': 'norm(k)', 'E': 'energy (eV)'}

            for c in concentrations:

                # plots of scalar properties first
                tp_c = tp + '_' + str(c)
                for x_value, y_values in [('k', temp_independent_k_props), ('E', temp_independent_E_props)]:
                    y_data_temp_independent = {'k': {'energy': self.kgrid[tp]['energy'][0],
                                                     'velocity': self.kgrid[tp]["norm(v)"][0]},
                                               'E': {'frequency': self.Efrequency[tp]}}
                    for y_value in y_values:
                        if not vec[y_value]:
                            plot_title = None
                            if y_value == 'frequency':
                                plot_title = 'Energy Histogram for {}, c={}'.format(self.tp_title[tp], c)
                            self.create_plots(x_axis_label[x_value], y_value, show_interactive, save_format, c, tp, tp_c,
                                              textsize, ticksize, path, margin_left,
                                              margin_bottom, fontfamily, x_data=x_data[x_value], y_data=y_data_temp_independent[x_value][y_value], x_label_short=x_value, plot_title=plot_title)

                for dir in direction:
                    y_data_temp_independent = {'k': {'energy': self.kgrid[tp]['energy'][0],
                                                     'velocity': self.kgrid[tp]["norm(v)"][0]},
                                               'E': {'frequency': self.Efrequency[tp],
                                                     'velocity': [self.get_scalar_output(p, dir) for p in self.egrid[tp]['velocity']]}}

                    tp_c_dir = tp_c + '_' + dir

                    # temperature independent k and E plots: energy(k), velocity(k), histogram(E), velocity(E)
                    for x_value, y_values in [('k', temp_independent_k_props), ('E', temp_independent_E_props)]:
                        for y_value in y_values:
                            if vec[y_value]:
                                self.create_plots(x_axis_label[x_value], y_value, show_interactive,
                                                  save_format, c, tp, tp_c_dir,
                                                  textsize, ticksize, path, margin_left,
                                                  margin_bottom, fontfamily, x_data=x_data[x_value],
                                                  y_data=y_data_temp_independent[x_value][y_value], x_label_short=x_value)

                    # want variable of the form: y_data_temp_dependent[k or E][prop][temp] (the following lines reorganize
                    # kgrid and egrid data)
                    y_data_temp_dependent = {'k': {prop: {T: [self.get_scalar_output(p, dir) for p in self.kgrid[tp][prop][c][T][0]]
                                                          for T in self.temperatures} for prop in temp_dependent_k_props},
                                             'E': {prop: {T: [self.get_scalar_output(p, dir) for p in self.egrid[tp][prop][c][T]]
                                                          for T in self.temperatures} for prop in temp_dependent_E_props}}

                    # temperature dependent k and E plots
                    for x_value, y_values in [('k', temp_dependent_k_props), ('E', temp_dependent_E_props)]:
                        for y_value in y_values:
                            all_plots = []
                            for T in self.temperatures:
                                all_plots.append({"x_col": x_data[x_value],
                                                  "y_col": y_data_temp_dependent[x_value][y_value][T],
                                                  "text": T, 'legend': str(T) + ' K', 'size': 6, "mode": "markers",
                                                  "color": "", "marker": temp_markers[T]})
                            self.create_plots(x_axis_label[x_value], y_value, show_interactive,
                                              save_format, c, tp, tp_c_dir,
                                              textsize, ticksize, path, margin_left,
                                              margin_bottom, fontfamily, all_plots=all_plots, x_label_short=x_value)

                    # mobility plots as a function of temperature (the only plot that does not have k or E on the x axis)
                    if mobility:
                        all_plots = []
                        for mo in mu_list:
                            all_plots.append({"x_col": self.temperatures,
                                              "y_col": [
                                                  abs(self.get_scalar_output(self.mobility[tp][mo][c][T], dir))
                                                  # I temporarily (for debugging purposes) added abs() for cases when mistakenly I get negative mobility values!
                                                  for T in self.temperatures],
                                              "text": mo, 'legend': mo, 'size': 6, "mode": "lines+markers",
                                              "color": "", "marker": mu_markers[mo]})
                        self.create_plots("Temperature (K)", "Mobility (cm2/V.s)", show_interactive,
                                          save_format, c, tp, tp_c_dir,
                                          textsize-5, ticksize-5, path, margin_left,
                                          margin_bottom, fontfamily, all_plots=all_plots, y_label_short="mobility", y_axis_type='log')



    def to_csv(self, path=None, csv_filename='AMSET_results.csv'):
        """
        this function writes the calculated transport properties to a csv file for convenience.
        :param csv_filename (str):
        :return:
        """
        import csv
        if not path:
            path = os.getcwd()

        with open(os.path.join(path, csv_filename), 'w') as csvfile:
            fieldnames = ['type', 'c(cm-3)', 'T(K)', 'overall', 'average'] + \
                         self.elastic_scatterings + self.inelastic_scatterings + ['seebeck']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for c in self.dopings:
                tp = self.get_tp(c)
                for T in self.temperatures:
                    row = {'type': tp, 'c(cm-3)': abs(c), 'T(K)': T}
                    for p in ['overall', 'average'] + self.elastic_scatterings + self.inelastic_scatterings:
                        row[p] = self.egrid["mobility"][p][c][T][tp]
                        #row[p] = sum(self.egrid["mobility"][p][c][T][tp]) / 3
                    row["seebeck"] = self.egrid["seebeck"][c][T][tp]
                    # row["seebeck"] = sum(self.egrid["seebeck"][c][T][tp]) / 3
                    writer.writerow(row)


    def test_run(self):
        self.kgrid_array = {}

        # points_1d = {dir: [-0.4 + i*0.1 for i in range(9)] for dir in ['x', 'y', 'z']}
        # points_1d = {dir: [-0.475 + i * 0.05 for i in range(20)] for dir in ['x', 'y', 'z']}
        points_1d = {dir: [] for dir in ['x', 'y', 'z']}
        # TODO: figure out which other points need a fine grid around them
        important_pts = [self.cbm_vbm["n"]["kpoint"]]
        if (np.array(self.cbm_vbm["p"]["kpoint"]) != np.array(self.cbm_vbm["n"]["kpoint"])).any():
            important_pts.append(self.cbm_vbm["p"]["kpoint"])

        for center in important_pts:
            for dim, dir in enumerate(['x', 'y', 'z']):
                points_1d[dir].append(center[dim])
                one_list = True
                if not one_list:
                    # for step, nsteps in [[0.0015, 3], [0.005, 4], [0.01, 4], [0.05, 2]]:
                    for step, nsteps in [[0.002, 2], [0.005, 4], [0.01, 4], [0.05, 2]]:
                        # for step, nsteps in [[0.01, 2]]:
                        # print "mesh: 10"
                        # loop goes from 0 to nsteps-2, so added values go from step to step*(nsteps-1)
                        for i in range(nsteps - 1):
                            points_1d[dir].append(center[dim] - (i + 1) * step)
                            points_1d[dir].append(center[dim] + (i + 1) * step)

                else:
                    # number of points options are: 175,616, 74,088, 15,625, 4,913
                    # for step in [0.001, 0.002, 0.0035, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.018, 0.021, 0.025, 0.03, 0.035, 0.0425, 0.05, 0.06, 0.075, 0.1, 0.125, 0.15, 0.18, 0.21, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]:
                    for step in [0.001, 0.002, 0.0035, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.07, 0.1,
                                 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45]:
                        # for step in [0.002, 0.005, 0.01, 0.015, 0.02, 0.03, 0.05, 0.1, 0.15, 0.25, 0.35, 0.45]:
                        # for step in [0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.35, 0.45]:
                        points_1d[dir].append(center[dim] + step)
                        points_1d[dir].append(center[dim] - step)

        # ensure all points are in first BZ
        for dir in ['x', 'y', 'z']:
            for ik1d in range(len(points_1d[dir])):
                if points_1d[dir][ik1d] > 0.5:
                    points_1d[dir][ik1d] -= 1
                if points_1d[dir][ik1d] <= -0.5:
                    points_1d[dir][ik1d] += 1
        # remove duplicates
        for dir in ['x', 'y', 'z']:
            points_1d[dir] = list(set(np.array(points_1d[dir]).round(decimals=14)))
        self.kgrid_array['k_points'] = self.create_grid(points_1d)
        kpts = self.array_to_kgrid(self.kgrid_array['k_points'])

        N = self.kgrid_array['k_points'].shape
        self.k_hat_grid = np.zeros(N)
        for i in range(N[0]):
            for j in range(N[1]):
                for k in range(N[2]):
                    k_vec = self.kgrid_array['k_points'][i, j, k]
                    if norm(k_vec) == 0:
                        self.k_hat_grid[i, j, k] = [0, 0, 0]
                    else:
                        self.k_hat_grid[i, j, k] = k_vec / norm(k_vec)

        self.dv_grid = self.find_dv(self.kgrid_array['k_points'])

        k_x = self.kgrid_array['k_points'][:, :, :, 0]
        k_y = self.kgrid_array['k_points'][:, :, :, 1]
        k_z = self.kgrid_array['k_points'][:, :, :, 2]
        result = self.integrate_over_k(np.cos(k_x))
        print(result)
        #print(self.kgrid_array['k_points'])


if __name__ == "__main__":
    # setting up inputs:
    logging.basicConfig(level=logging.DEBUG)
    mass = 0.25
    use_poly_bands = False

    model_params = {"bs_is_isotropic": True, "elastic_scatterings": ["ACD", "IMP", "PIE"],
                    "inelastic_scatterings": ["POP"] }
    if use_poly_bands:
        model_params["poly_bands"] = [[[[0.0, 0.0, 0.0], [0.0, mass]]]]

    performance_params = {"dE_min": 0.0001, "nE_min": 2, "parallel": True, "BTE_iters": 5}

    ### for PbTe
    # material_params = {"epsilon_s": 44.4, "epsilon_inf": 25.6, "W_POP": 10.0, "C_el": 128.8,
    #                "E_D": {"n": 4.0, "p": 4.0}}
    # cube_path = "../test_files/PbTe/nscf_line"
    # coeff_file = os.path.join(cube_path, "..", "fort.123")
    # #coeff_file = os.path.join(cube_path, "fort.123")

    ## For GaAs
    material_params = {"epsilon_s": 12.9, "epsilon_inf": 10.9, "W_POP": 8.73, "C_el": 139.7,
                       "E_D": {"n": 8.6, "p": 8.6}, "P_PIE": 0.052, "scissor":  0.5818}
    cube_path = "../test_files/GaAs/"
    #####coeff_file = os.path.join(cube_path, "fort.123_GaAs_k23")
    coeff_file = os.path.join(cube_path, "fort.123_GaAs_1099kp") # good results!
    # coeff_file = os.path.join(cube_path, "fort.123_GaAs_sym_23x23x23") # bad results! (because the fitting not good)
    # coeff_file = os.path.join(cube_path, "fort.123_GaAs_11x11x11_ISYM0") # good results

    ### For Si
    # material_params = {"epsilon_s": 11.7, "epsilon_inf": 11.6, "W_POP": 15.23, "C_el": 190.2,
    #                    "E_D": {"n": 6.5, "p": 6.5}, "P_PIE": 0.01, "scissor": 0.5154}
    # cube_path = "../test_files/Si/"
    # coeff_file = os.path.join(cube_path, "Si_fort.123")

    AMSET = AMSET(calc_dir=cube_path, material_params=material_params,
                  model_params=model_params, performance_params=performance_params,
                  dopings = [-2e15], temperatures = [300], k_integration=True, e_integration=True, fermi_type='e'
                  )   # -3.3e13
    cProfile.run('AMSET.run(coeff_file=coeff_file, kgrid_tp="coarse")')

    AMSET.write_input_files()
    AMSET.to_csv()
    # AMSET.plot(k_plots=['energy'], E_plots='all', show_interactive=True,
    #            carrier_types=AMSET.all_types, save_format=None)

    AMSET.to_json(kgrid=True, trimmed=True, max_ndata=100, nstart=0)
