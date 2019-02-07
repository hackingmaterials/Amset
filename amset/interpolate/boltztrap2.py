"""
Class to interpolate a band structure using BoltzTraP2
"""

import numpy as np

from typing import Optional, Union, List, Tuple

from BoltzTraP2 import sphere, fite

from amset.utils.constants import Hartree_to_eV, hbar, A_to_m, m_to_cm, m_e, e
from pymatgen import Spin
from pymatgen.electronic_structure.boltztrap2 import BandstructureLoader
from amset.interpolate.base import AbstractInterpolater

__author__ = "Alex Ganose, Francesco Ricci and Alireza Faghaninia"
__copyright__ = "Copyright 2019, HackingMaterials"
__maintainer__ = "Alex Ganose"


class BoltzTraP2Interpolater(AbstractInterpolater):
    """Class to interpolate band structures based on BoltzTraP2.

    Details of the interpolation method are available in:

    3. Madsen, G. K. & Singh, D. J. Computer Physics Communications 175, 67–71
       (2006)
    3. Madsen, G. K., Carrete, J., and Verstraete, M. J. Computer Physics
        Communications 231, 140–145 (2018)

    Args:
        band_structure (BandStructure): A pymatgen band structure object.
        num_electrons (num_electrons): The number of electrons in the system.
    """

    def __init__(self, band_structure, num_electrons, **kwargs):
        super(BoltzTraP2Interpolater, self).__init__(
            band_structure, num_electrons, **kwargs)
        self._parameters = None

    def initialize(self):
        """Initialise the interpolater.

        This will run BoltzTraP2 to generate the band structure coefficients
        needed for interpolation.
        """
        bz2_data = BandstructureLoader(
            self._band_structure, structure=self._band_structure.structure,
            nelect=self._num_electrons)
        equivalences = sphere.get_equivalences(
            atoms=bz2_data.atoms, nkpt=len(bz2_data.kpoints) * 5,
            magmom=None)
        lattvec = bz2_data.get_lattvec()
        coeffs = fite.fitde3D(bz2_data, equivalences)

        self._parameters = (equivalences, lattvec, coeffs)

    def get_energies(self, kpoints: np.ndarray,
                     iband: Optional[Union[int, List[int]]] = None,
                     scissor: float = 0.0,
                     return_velocity: bool = False,
                     return_effective_mass: bool = False
                     ) -> Union[np.ndarray, Tuple[np.ndarray]]:
        """Gets the interpolated energies for multiple k-points in a band.

        Args:
            kpoints: The k-points in fractional coordinates.
            iband: A band index or list of band indicies for which to get the
                energies. Band indices are 0-indexed unlike in BoltzTraP1 where
                they are 1 indexed. If ``None``, the energies for all
                available bands will be returned.
            scissor: The amount by which the band gap is scissored.
            return_velocity: Whether to return the band velocities.
            return_effective_mass: Whether to return the band effective masses.

        Returns:
            The band energies as a numpy array. If iband is an integer
            (only 1 band requested), the energies will be returned as a
            np.ndarray array with shape (num_kpoints). If multiple bands are
            requested, the energies will be returned as a np.ndarray
            with shape (num_bands, num_kpoints). If ``return_velocity`` or
            ``return_effective_mass`` are ``True`` a tuple is returned,
            formatted as::

                (energies, Optional[velocities], Optional[effective_masses])

            The velocities and effective masses are given as the 1x3 trace and
            full 3x3 tensor, respectively (along cartesian directions).
        """
        if not self._parameters:
            self.initialize()

        if isinstance(iband, int):
            iband = [iband]
        elif not iband:
            iband = list(range(len(self._parameters[2])))

        fitted = fite.getBands(np.array(kpoints), *self._parameters,
                               curvature=return_effective_mass)

        energies = fitted[0][iband] * Hartree_to_eV

        # BoltzTraP2 energies can be shifted slighty relative to the vasprun
        # eigenvalues here we shift the energies back in line
        energies += (self._band_structure.bands[Spin.up][iband[0]][0] -
                     energies[0][0])

        # Apply scissor; shift will be zero if scissor is 0
        # TODO: Make compatible with spin polarization
        vbm = max(self._band_structure.get_vbm()['band_index'][Spin.up])
        energies += np.array([[(1 if band_index > vbm else -1) * scissor / 2
                               for _ in kpoints] for band_index in iband])

        shape = (len(iband), len(kpoints)) if len(iband) > 1 else (
            len(kpoints),)
        to_return = [energies.reshape(shape)]

        if return_velocity:
            factor = Hartree_to_eV * m_to_cm * A_to_m / (hbar * 0.52917721067)
            matrix_norm = (self._lattice_matrix / np.linalg.norm(
                self._lattice_matrix))
            velocities = fitted[1][:, iband, :].transpose((1, 0, 2))
            velocities = abs(np.matmul(matrix_norm, velocities)) * factor
            velocities = velocities.transpose((0, 2, 1))
            to_return.append(velocities.reshape(shape + velocities.shape[2:]))

        if return_effective_mass:
            factor = 0.52917721067 ** 2 * e * hbar ** 2 / (
                    Hartree_to_eV * A_to_m ** 2 * m_e)
            effective_masses = fitted[2][:, :, iband, :].transpose(1, 0, 2, 3)
            effective_masses = factor / effective_masses
            effective_masses = effective_masses.transpose((2, 3, 0, 1))
            to_return.append(effective_masses.reshape(
                shape + effective_masses.shape[2:]))

        return self._simplify_return_data(to_return)
