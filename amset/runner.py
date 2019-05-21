import copy
import datetime
import logging

import numpy as np

from pathlib import Path
from typing import Optional, Any, Dict, Union, List

from monty.json import MSONable

from amset.interpolate import Interpolater
from pymatgen.electronic_structure.bandstructure import BandStructure
from pymatgen.io.vasp import Vasprun
from amset import __version__, amset_defaults

logger = logging.getLogger(__name__)


class AmsetRunner(MSONable):

    def __init__(self,
                 band_structure: BandStructure,
                 num_electrons: int,
                 material_parameters: Dict[str, Any],
                 doping: Optional[Union[List, np.ndarray]] = None,
                 temperatures: Optional[Union[List, np.ndarray]] = None,
                 scattering: Optional[Union[str, List[str], float]] = "auto",
                 performance_parameters: Optional[Dict[str, float]] = None,
                 interpolation_factor: int = 10,
                 scissor: Optional[float] = None,
                 user_bandgap: Optional[float] = None,
                 soc: bool = False):
        self._band_structure = band_structure
        self._num_electrons = num_electrons
        self.scattering = scattering
        self.interpolation_factor = interpolation_factor
        self._scissor = scissor
        self._user_bandgap = user_bandgap
        self._soc = soc
        self.doping = doping
        self.temperatures = temperatures

        if not self.doping:
            self.doping = np.concatenate([np.logspace(16, 21, 6),
                                          -np.logspace(16, 21, 6)])

        if not self.temperatures:
            self.temperatures = np.array([300])

        # set materials and performance parameters
        # if the user doesn't specify a value then use the default
        params = copy.deepcopy(amset_defaults)
        self.performance_parameters = params["performance"]
        self.material_parameters = params["materials"]
        self.performance_parameters.update(performance_parameters)
        self.material_parameters.update(material_parameters)

    def run(self,
            directory: Union[str, Path] = '.',
            prefix: Optional[str] = None,
            write_input: bool = True,
            write_mesh: bool = True):

        _log_amset_intro()
        # _log_scattering_check(self.scattering, self.material_parameters)
        # _log_structure_information(self._band_structure)
        # _log_settings(self)

        interpolater = Interpolater(
            self._band_structure, num_electrons=self._num_electrons,
            interpolation_factor=self.interpolation_factor, soc=self._soc,
            interpolate_projections=True)

        electronic_structure = interpolater.get_electronic_structure(
            energy_cutoff=self.performance_parameters,
            scissor=self._scissor, bandgap=self._user_bandgap,
            dos_estep=self.performance_parameters["dos_estep"],
            dos_width=self.performance_parameters["dos_width"],
            symprec=self.performance_parameters["symprec"],
            nworkers=self.performance_parameters["nworkers"])

    @staticmethod
    def from_vasprun(vasprun: Union[str, Path, Vasprun],
                     material_parameters: Dict[str, Any],
                     **kwargs) -> "AmsetRunner":
        """Initialise an AmsetRunner from a Vasprun.

        The nelect and soc options will be determined from the Vasprun
        automatically.

        Args:
            vasprun: Path to a vasprun or a Vasprun pymatgen object.
            material_parameters: TODO
            **kwargs: Other parameters to be passed to the AmsetRun constructor
                except ``nelect`` and ``soc``.

        Returns:
            An :obj:`AmsetRunner` instance.
        """
        if not isinstance(vasprun, Vasprun):
            vasprun = Vasprun(vasprun, parse_projected_eigen=True)

        band_structure = vasprun.get_band_structure()
        soc = vasprun.parameters["LSORBIT"]
        nelect = vasprun.parameters["NELECT"]

        return AmsetRunner(band_structure, nelect, material_parameters,
                           soc=soc, **kwargs)


def _log_amset_intro():
    now = datetime.datetime.now()
    logger.info("""
                █████╗ ███╗   ███╗███████╗███████╗████████╗
               ██╔══██╗████╗ ████║██╔════╝██╔════╝╚══██╔══╝
               ███████║██╔████╔██║███████╗█████╗     ██║   
               ██╔══██║██║╚██╔╝██║╚════██║██╔══╝     ██║   
               ██║  ██║██║ ╚═╝ ██║███████║███████╗   ██║   
               ╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝   ╚═╝   
               
                                             v{}
                                             
    A. Ganose, A. Faghaninia, J. Park, F. Ricci, R. Woods-Robinson, 
    J. Frost,  K. Persson, G. Hautier, A. Jain, in prep.
    
    
    amset starting on {} at {}""".format(
        __version__, now.strftime("%d %b %Y"), now.strftime("%H:%M")))

