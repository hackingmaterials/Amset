import os
import unittest
import numpy as np

from numpy.testing import assert_array_equal

from amset.interpolation.interpolate import Interpolater, _get_kpoints
from amset.misc.log import initialize_amset_logger
from amset.misc.util import get_dense_kpoint_mesh_spglib
from pymatgen import Spin
from pymatgen.io.vasp import Vasprun

test_dir = os.path.dirname(os.path.abspath(__file__))
amset_files = os.path.join(test_dir, '..', '..', '..', 'examples',
                           'GaAs')


class TestBoltzTraP2Interpolater(unittest.TestCase):
    """Tests for interpolating a band structure using BoltzTraP2."""

    def setUp(self):
        vr = Vasprun(os.path.join(amset_files, 'vasprun.xml.gz'),
                     parse_projected_eigen=True)
        bs = vr.get_band_structure()
        num_electrons = vr.parameters['NELECT']

        self.kpoints = np.array(vr.actual_kpoints)
        self.interpolater = Interpolater(
            bs, num_electrons, interpolate_projections=True,
            interpolation_factor=1)

    def test_initialisation(self):
        """Test coefficients and parameters are calculated correctly."""
        self.interpolater.initialize()
        params = self.interpolater._parameters
        assert_array_equal(params[0][0], [[0, 0, 0]])
        self.assertAlmostEqual(params[1][0][0], 9.14055614)
        self.assertAlmostEqual(params[2][0][0].real, -2.33144546)

    def test_get_energies(self):
        """Test getting the interpolated energy, velocity and effective mass."""

        # test just getting energy
        energies = self.interpolater.get_energies(
            self.kpoints, 25, return_velocity=False,
            return_effective_mass=False)
        self.assertEqual(energies.shape, (138,))
        self.assertAlmostEqual(energies[0], 3.852399483908641)

        # test energy + velocity
        energies, velocities = self.interpolater.get_energies(
            self.kpoints, 25, return_velocity=True,
            return_effective_mass=False)
        self.assertEqual(energies.shape, (138,))
        self.assertAlmostEqual(energies[0], 3.852399483908641)
        self.assertEqual(velocities.shape, (138, 3))
        self.assertAlmostEqual(velocities[10][0], 5.401166156893334e+6,
                               places=0)

        # test energy + effective_mass
        energies, effective_masses = self.interpolater.get_energies(
            self.kpoints, 25, return_velocity=False,
            return_effective_mass=True)
        self.assertEqual(energies.shape, (138,))
        self.assertAlmostEqual(energies[0], 3.852399483908641)
        self.assertEqual(effective_masses.shape, (138, 3, 3))
        self.assertAlmostEqual(effective_masses[10][0][0], 0.2242569613626494)

        # test energy + velocity + effective_mass
        energies, velocities, effective_masses = self.interpolater.get_energies(
            self.kpoints, 25, return_velocity=True,
            return_effective_mass=True)
        self.assertEqual(energies.shape, (138,))
        self.assertAlmostEqual(energies[0], 3.852399483908641)
        self.assertEqual(velocities.shape, (138, 3))
        self.assertAlmostEqual(velocities[10][0], 5.401166156893334e+6,
                               places=0)
        self.assertEqual(effective_masses.shape, (138, 3, 3))
        self.assertAlmostEqual(effective_masses[10][0][0], 0.2242569613626494)

    def test_get_energies_scissor(self):
        """Test scissoring of band energies."""

        # test valence band
        energies = self.interpolater.get_energies(
            self.kpoints, 25, return_velocity=False,
            return_effective_mass=False, scissor=1.)
        self.assertEqual(energies.shape, (138,))
        self.assertAlmostEqual(energies[0], 3.852399483908641 - 0.5)

        # test conduction band
        energies = self.interpolater.get_energies(
            self.kpoints, 33, return_velocity=False,
            return_effective_mass=False, scissor=1.)
        self.assertEqual(energies.shape, (138,))
        self.assertAlmostEqual(energies[0], 7.301700765 + 0.5)

    def test_get_energies_multiple_bands(self):
        """Test getting the interpolated data for multiple bands."""
        # test just getting energy
        energies = self.interpolater.get_energies(
            self.kpoints, [25, 35], return_velocity=False,
            return_effective_mass=False)
        self.assertEqual(energies.shape, (2, 138,))
        self.assertAlmostEqual(energies[0][0], 3.852399483908641)
        self.assertAlmostEqual(energies[1][0], 9.594401616456384)

        # test energy + velocity
        energies, velocities = self.interpolater.get_energies(
            self.kpoints, [25, 35], return_velocity=True,
            return_effective_mass=False)
        self.assertEqual(energies.shape, (2, 138,))
        self.assertAlmostEqual(energies[0][0], 3.852399483908641)
        self.assertAlmostEqual(energies[1][0], 9.594401616456384)
        self.assertEqual(velocities.shape, (2, 138, 3))
        self.assertAlmostEqual(velocities[0][10][0], 5.401166156893334e+6,
                               places=0)
        self.assertAlmostEqual(velocities[1][10][0], 1.1686720831758736e+8,
                               places=0)

        # test energy + effective_mass
        energies, effective_masses = self.interpolater.get_energies(
            self.kpoints, [25, 35], return_velocity=False,
            return_effective_mass=True)
        self.assertEqual(energies.shape, (2, 138,))
        self.assertAlmostEqual(energies[0][0], 3.852399483908641)
        self.assertAlmostEqual(energies[1][0], 9.594401616456384)
        self.assertEqual(effective_masses.shape, (2, 138, 3, 3))
        self.assertAlmostEqual(effective_masses[0][10][0][0], 0.224256961362649)
        self.assertAlmostEqual(effective_masses[1][10][0][0], 0.009057103344700)

        # test energy + velocity + effective_mass
        energies, velocities, effective_masses = self.interpolater.get_energies(
            self.kpoints, [25, 35], return_velocity=True,
            return_effective_mass=True)
        self.assertEqual(energies.shape, (2, 138,))
        self.assertAlmostEqual(energies[0][0], 3.852399483908641)
        self.assertAlmostEqual(energies[1][0], 9.594401616456384)
        self.assertEqual(velocities.shape, (2, 138, 3))
        self.assertAlmostEqual(velocities[0][10][0], 5.401166156893334e+6,
                               places=0)
        self.assertAlmostEqual(velocities[1][10][0], 1.1686720831758736e+8,
                               places=0)
        self.assertEqual(effective_masses.shape, (2, 138, 3, 3))
        self.assertAlmostEqual(effective_masses[0][10][0][0], 0.224256961362649)
        self.assertAlmostEqual(effective_masses[1][10][0][0], 0.009057103344700)

    def test_get_energies_all_bands(self):
        # test all bands
        energies, velocities, effective_masses = self.interpolater.get_energies(
            self.kpoints, None, return_velocity=True,
            return_effective_mass=True)
        self.assertEqual(energies.shape, (96, 138,))
        self.assertAlmostEqual(energies[25][0], 3.852399483908641)
        self.assertAlmostEqual(energies[35][0], 9.594401616456384)
        self.assertEqual(velocities.shape, (96, 138, 3))
        self.assertAlmostEqual(velocities[25][10][0], 5.401166156893334e+6,
                               places=0)
        self.assertAlmostEqual(velocities[35][10][0], 1.1686720831758736e+8,
                               places=0)
        self.assertEqual(effective_masses.shape, (96, 138, 3, 3))
        self.assertAlmostEqual(effective_masses[25][10][0][0], 0.22425696136264)
        self.assertAlmostEqual(effective_masses[35][10][0][0], 0.00905710334470)

    def test_get_dos(self):
        """Test generating the interpolated DOS."""
        dos = self.interpolater.get_dos([10, 10, 10], emin=-10, emax=10,
                                        width=0.075)
        self.assertEqual(dos.shape, (20000, 2))
        self.assertEqual(dos[0][0], -10)
        self.assertAlmostEqual(dos[15000][1], 3.5362612128412807)

    def test_get_extrema(self):
        """Test getting the band structure extrema."""

        # test VBM
        extrema = self.interpolater.get_extrema(31, e_cut=1.)
        np.testing.assert_array_almost_equal(extrema[0], [0., 0.0, 0.0], 10)
        np.testing.assert_array_almost_equal(extrema[1],
                                             [0.0972, 0.4028, 0.0972], 4)
        np.testing.assert_array_almost_equal(extrema[2],
                                             [0.5, 0.5, -0.5], 10)
        np.testing.assert_array_almost_equal(extrema[3],
                                             [-0.0365, 0.0365, 0.5], 4)

        # test CBM
        extrema = self.interpolater.get_extrema(32, e_cut=1.)
        np.testing.assert_array_almost_equal(extrema[0], [0., 0.0, 0.0], 10)
        np.testing.assert_array_almost_equal(extrema[1], [0., 0.0, 0.5], 10)
        np.testing.assert_array_almost_equal(extrema[2],
                                             [0.5, 0.5, -0.5], 4)
        np.testing.assert_array_almost_equal(extrema[3],
                                             [0.4167, 0.4167, -0.0019], 4)

    def test_get_energies_symprec(self):
        kpoints = get_dense_kpoint_mesh_spglib([13, 15, 29],
                                               spg_order=False, shift=0)

        initialize_amset_logger()

        energies, velocities, projections, sym_info = self.interpolater.get_energies(
            kpoints, None, return_velocity=True, atomic_units=True,
            return_effective_mass=False, return_projections=True, symprec=0.1,
            return_vel_outer_prod=True, return_kpoint_mapping=True)

        energies_no_sym, velocities_no_sym, projections_no_sym = \
            self.interpolater.get_energies(
                kpoints, None, return_velocity=True, atomic_units=True,
                return_effective_mass=False, return_projections=True,
                return_vel_outer_prod=True,
                symprec=None)

        np.testing.assert_array_almost_equal(
            energies[Spin.up], energies_no_sym[Spin.up])
        np.testing.assert_array_almost_equal(
            velocities[Spin.up], velocities_no_sym[Spin.up])

        for l in projections[Spin.up]:
            np.testing.assert_array_almost_equal(
                projections[Spin.up][l],
                projections_no_sym[Spin.up][l])

    def test_get_energies_interpolater(self):

        initialize_amset_logger()

        amset_data = self.interpolater.get_amset_data()

        energies, velocities, projections, sym_info = \
            self.interpolater.get_energies(
                amset_data.full_kpoints, None, return_velocity=True,
                atomic_units=True, return_effective_mass=False,
                return_projections=True, symprec=0.1,
                return_vel_outer_prod=True, return_kpoint_mapping=True)

        np.testing.assert_array_almost_equal(
            energies[Spin.up], amset_data.energies[Spin.up])
        np.testing.assert_array_almost_equal(
            velocities[Spin.up], amset_data.velocities_product[Spin.up])

        for l in projections[Spin.up]:
            np.testing.assert_array_almost_equal(
                projections[Spin.up][l],
                amset_data._projections[Spin.up][l])

        np.testing.assert_array_equal(sym_info["ir_kpoints_idx"],
                                      amset_data.ir_kpoints_idx)
        np.testing.assert_array_equal(sym_info["ir_to_full_idx"],
                                      amset_data.ir_to_full_kpoint_mapping)

