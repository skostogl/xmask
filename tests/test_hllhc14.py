import yaml
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd
from scipy.constants import c as clight

from cpymad.madx import Madx
import xtrack as xt
import xfields as xf

import xmask as xm
import xmask.lhc as xmlhc

from _complementary_hllhc14 import (build_sequence, apply_optics,
                                    check_optics_orbit_etc, orbit_correction_config,
                                    knob_settings_yaml_str, knob_names_yaml_str,
                                    tune_chroma_yaml_str, _get_z_centroids,
                                    leveling_yaml_str)

# We assume that the tests will be run in order. In case of issues we could use
# https://pypi.org/project/pytest-order/ to enforce the order.

test_data_dir = Path(__file__).parent.parent / "test_data"

def test_hllhc14_0_create_collider():
    # Make mad environment
    xm.make_mad_environment(links={
        'acc-models-lhc': str(test_data_dir / 'hllhc14')})

    # Start mad
    mad_b1b2 = Madx(command_log="mad_collider.log")
    mad_b4 = Madx(command_log="mad_b4.log")

    # Build sequences
    build_sequence(mad_b1b2, mylhcbeam=1)
    build_sequence(mad_b4, mylhcbeam=4)

    # Apply optics (only for b1b2, b4 will be generated from b1b2)
    apply_optics(mad_b1b2,
        optics_file="acc-models-lhc/round/opt_round_150_1500_thin.madx")

    # Build xsuite collider
    collider = xmlhc.build_xsuite_collider(
        sequence_b1=mad_b1b2.sequence.lhcb1,
        sequence_b2=mad_b1b2.sequence.lhcb2,
        sequence_b4=mad_b4.sequence.lhcb2,
        beam_config={'lhcb1':{'beam_energy_tot': 7000},
                     'lhcb2':{'beam_energy_tot': 7000}},
        enable_imperfections=False,
        enable_knob_synthesis='_mock_for_testing',
        rename_coupling_knobs=True,
        pars_for_imperfections={},
        ver_lhc_run=None,
        ver_hllhc_optics=1.4)

    assert len(collider.lines.keys()) == 4

    collider.to_json('collider_hllhc14_00.json')

def test_hllhc14_1_install_beambeam():

    collider = xt.Multiline.from_json('collider_hllhc14_00.json')

    collider.install_beambeam_interactions(
    clockwise_line='lhcb1',
    anticlockwise_line='lhcb2',
    ip_names=['ip1', 'ip2', 'ip5', 'ip8'],
    delay_at_ips_slots=[0, 891, 0, 2670],
    num_long_range_encounters_per_side={
        'ip1': 25, 'ip2': 20, 'ip5': 25, 'ip8': 20},
    num_slices_head_on=11,
    harmonic_number=35640,
    bunch_spacing_buckets=10,
    sigmaz=0.076)

    collider.to_json('collider_hllhc14_01.json')

    # Check integrity of the collider after installation

    collider_before_save = collider
    dct = collider.to_dict()
    collider = xt.Multiline.from_dict(dct)
    collider.build_trackers()

    assert collider._bb_config['dataframes']['clockwise'].shape == (
        collider_before_save._bb_config['dataframes']['clockwise'].shape)
    assert collider._bb_config['dataframes']['anticlockwise'].shape == (
        collider_before_save._bb_config['dataframes']['anticlockwise'].shape)

    assert (collider._bb_config['dataframes']['clockwise']['elementName'].iloc[50]
        == collider_before_save._bb_config['dataframes']['clockwise']['elementName'].iloc[50])
    assert (collider._bb_config['dataframes']['anticlockwise']['elementName'].iloc[50]
        == collider_before_save._bb_config['dataframes']['anticlockwise']['elementName'].iloc[50])

    # Put in some orbit
    knobs = dict(on_x1=250, on_x5=-200, on_disp=1)

    for kk, vv in knobs.items():
        collider.vars[kk] = vv

    tw1_b1 = collider['lhcb1'].twiss(method='4d')
    tw1_b2 = collider['lhcb2'].twiss(method='4d')

    collider_ref = xt.Multiline.from_json('collider_hllhc14_00.json')

    collider_ref.build_trackers()

    for kk, vv in knobs.items():
        collider_ref.vars[kk] = vv

    tw0_b1 = collider_ref['lhcb1'].twiss(method='4d')
    tw0_b2 = collider_ref['lhcb2'].twiss(method='4d')

    assert np.isclose(tw1_b1.qx, tw0_b1.qx, atol=1e-7, rtol=0)
    assert np.isclose(tw1_b1.qy, tw0_b1.qy, atol=1e-7, rtol=0)
    assert np.isclose(tw1_b2.qx, tw0_b2.qx, atol=1e-7, rtol=0)
    assert np.isclose(tw1_b2.qy, tw0_b2.qy, atol=1e-7, rtol=0)

    assert np.isclose(tw1_b1.dqx, tw0_b1.dqx, atol=1e-4, rtol=0)
    assert np.isclose(tw1_b1.dqy, tw0_b1.dqy, atol=1e-4, rtol=0)
    assert np.isclose(tw1_b2.dqx, tw0_b2.dqx, atol=1e-4, rtol=0)
    assert np.isclose(tw1_b2.dqy, tw0_b2.dqy, atol=1e-4, rtol=0)

    for ipn in [1, 2, 3, 4, 5, 6, 7, 8]:
        assert np.isclose(tw1_b1['betx', f'ip{ipn}'], tw0_b1['betx', f'ip{ipn}'], rtol=1e-5, atol=0)
        assert np.isclose(tw1_b1['bety', f'ip{ipn}'], tw0_b1['bety', f'ip{ipn}'], rtol=1e-5, atol=0)
        assert np.isclose(tw1_b2['betx', f'ip{ipn}'], tw0_b2['betx', f'ip{ipn}'], rtol=1e-5, atol=0)
        assert np.isclose(tw1_b2['bety', f'ip{ipn}'], tw0_b2['bety', f'ip{ipn}'], rtol=1e-5, atol=0)

        assert np.isclose(tw1_b1['px', f'ip{ipn}'], tw0_b1['px', f'ip{ipn}'], rtol=1e-9, atol=0)
        assert np.isclose(tw1_b1['py', f'ip{ipn}'], tw0_b1['py', f'ip{ipn}'], rtol=1e-9, atol=0)
        assert np.isclose(tw1_b2['px', f'ip{ipn}'], tw0_b2['px', f'ip{ipn}'], rtol=1e-9, atol=0)
        assert np.isclose(tw1_b2['py', f'ip{ipn}'], tw0_b2['py', f'ip{ipn}'], rtol=1e-9, atol=0)

        assert np.isclose(tw1_b1['s', f'ip{ipn}'], tw0_b1['s', f'ip{ipn}'], rtol=1e-10, atol=0)
        assert np.isclose(tw1_b2['s', f'ip{ipn}'], tw0_b2['s', f'ip{ipn}'], rtol=1e-10, atol=0)

def test_hllhc14_2_tuning():

    collider = xt.Multiline.from_json('collider_hllhc14_01.json')

    knob_settings = yaml.safe_load(knob_settings_yaml_str)
    tune_chorma_targets = yaml.safe_load(tune_chroma_yaml_str)
    knob_names_lines = yaml.safe_load(knob_names_yaml_str)

    # Set all knobs (crossing angles, dispersion correction, rf, crab cavities,
    # experimental magnets, etc.)
    for kk, vv in knob_settings.items():
        collider.vars[kk] = vv

    # Build trackers
    collider.build_trackers()

    # Check coupling knobs are responding
    collider.vars['c_minus_re_b1'] = 1e-3
    collider.vars['c_minus_im_b1'] = 1e-3
    assert np.isclose(collider['lhcb1'].twiss().c_minus, 1.4e-3,
                      rtol=0, atol=2e-4)
    assert np.isclose(collider['lhcb2'].twiss().c_minus, 0,
                      rtol=0, atol=2e-4)
    collider.vars['c_minus_re_b1'] = 0
    collider.vars['c_minus_im_b1'] = 0
    collider.vars['c_minus_re_b2'] = 1e-3
    collider.vars['c_minus_im_b2'] = 1e-3
    assert np.isclose(collider['lhcb1'].twiss().c_minus, 0,
                        rtol=0, atol=2e-4)
    assert np.isclose(collider['lhcb2'].twiss().c_minus, 1.4e-3,
                        rtol=0, atol=2e-4)
    collider.vars['c_minus_re_b2'] = 0
    collider.vars['c_minus_im_b2'] = 0

    # Introduce some coupling to check correction
    collider.vars['c_minus_re_b1'] = 0.4e-3
    collider.vars['c_minus_im_b1'] = 0.7e-3
    collider.vars['c_minus_re_b2'] = 0.5e-3
    collider.vars['c_minus_im_b2'] = 0.6e-3

    # Tunings
    for line_name in ['lhcb1', 'lhcb2']:

        knob_names = knob_names_lines[line_name]

        targets = {
            'qx': tune_chorma_targets['qx'][line_name],
            'qy': tune_chorma_targets['qy'][line_name],
            'dqx': tune_chorma_targets['dqx'][line_name],
            'dqy': tune_chorma_targets['dqy'][line_name],
        }

        xm.machine_tuning(line=collider[line_name],
            enable_closed_orbit_correction=True,
            enable_linear_coupling_correction=True,
            enable_tune_correction=True,
            enable_chromaticity_correction=True,
            knob_names=knob_names,
            targets=targets,
            line_co_ref=collider[line_name+'_co_ref'],
            co_corr_config=orbit_correction_config[line_name])

    collider.to_json('collider_hllhc14_02.json')

    # Check optics, orbit, rf, etc.
    check_optics_orbit_etc(collider, line_names=['lhcb1', 'lhcb2'],
                           sep_h_ip2=-0.138e-3, sep_v_ip8=-0.043e-3) # Setting in yaml file

def test_hllhc14_3_level_ip2_ip8():

    # Load collider and build trackers
    collider = xt.Multiline.from_json('collider_hllhc14_02.json')
    collider.build_trackers()

    config = yaml.safe_load(leveling_yaml_str)
    config_lumi_leveling = config['config_lumi_leveling']
    config_beambeam = config['config_beambeam']

    xmlhc.luminosity_leveling(
        collider, config_lumi_leveling=config_lumi_leveling,
        config_beambeam=config_beambeam)

    # Re-match tunes, and chromaticities
    tune_chorma_targets = yaml.safe_load(tune_chroma_yaml_str)
    knob_names_lines = yaml.safe_load(knob_names_yaml_str)

    for line_name in ['lhcb1', 'lhcb2']:
        knob_names = knob_names_lines[line_name]
        targets = {
            'qx': tune_chorma_targets['qx'][line_name],
            'qy': tune_chorma_targets['qy'][line_name],
            'dqx': tune_chorma_targets['dqx'][line_name],
            'dqy': tune_chorma_targets['dqy'][line_name],
        }
        xm.machine_tuning(line=collider[line_name],
            enable_tune_correction=True, enable_chromaticity_correction=True,
            knob_names=knob_names, targets=targets)

    collider.to_json('collider_hllhc14_03.json')

    # Checks
    import numpy as np
    tw = collider.twiss(lines=['lhcb1', 'lhcb2'])

    # Check luminosity in ip8
    ll_ip8 = xt.lumi.luminosity_from_twiss(
        n_colliding_bunches=2572,
        num_particles_per_bunch=2.2e11,
        ip_name='ip8',
        nemitt_x=2.5e-6,
        nemitt_y=2.5e-6,
        sigma_z=0.076,
        twiss_b1=tw.lhcb1,
        twiss_b2=tw.lhcb2,
        crab=False)

    assert np.isclose(ll_ip8, 2e33, rtol=1e-2, atol=0)

    # Check separation in ip2
    mean_betx = np.sqrt(tw['lhcb1']['betx', 'ip2']
                    *tw['lhcb2']['betx', 'ip2'])
    gamma0 = tw['lhcb1'].particle_on_co.gamma0[0]
    beta0 = tw['lhcb1'].particle_on_co.beta0[0]
    sigmax = np.sqrt(2.5e-6 * mean_betx /gamma0 / beta0)

    assert np.isclose(collider.vars['on_sep2']._value/1000,
                      5 * sigmax / 2, rtol=1e-3, atol=0)

    # Check optics, orbit, rf, etc.
    check_optics_orbit_etc(collider, line_names=['lhcb1', 'lhcb2'],
                           # From lumi leveling
                           sep_h_ip2=-0.00014330344100935583, # checked against normalized sep
                           sep_v_ip8=-3.441222062677253e-05, # checked against lumi
                           )

def test_hllhc14_4_bb_config():

    collider = xt.Multiline.from_json('collider_hllhc14_03.json')
    collider.build_trackers()

    collider.configure_beambeam_interactions(
        num_particles=2.2e11,
        nemitt_x=2e-6, nemitt_y=3e-6)

    collider.to_json('collider_hllhc14_04.json')

    ip_bb_config= {
        'ip1': {'num_lr_per_side': 25},
        'ip2': {'num_lr_per_side': 20},
        'ip5': {'num_lr_per_side': 25},
        'ip8': {'num_lr_per_side': 20},
    }

    line_config = {
        'lhcb1': {'strong_beam': 'lhcb2', 'sorting': {'l': -1, 'r': 1}},
        'lhcb2': {'strong_beam': 'lhcb1', 'sorting': {'l': 1, 'r': -1}},
    }

    nemitt_x = 2e-6
    nemitt_y = 3e-6
    harmonic_number = 35640
    bunch_spacing_buckets = 10
    sigmaz = 0.076
    num_slices_head_on = 11
    num_particles = 2.2e11
    qx_no_bb = {'lhcb1': 62.31, 'lhcb2': 62.315}
    qy_no_bb = {'lhcb1': 60.32, 'lhcb2': 60.325}

    for line_name in ['lhcb1', 'lhcb2']:

        print(f'Global check on line {line_name}')

        # Check that the number of lenses is correct
        df = collider[line_name].to_pandas()
        bblr_df = df[df['element_type'] == 'BeamBeamBiGaussian2D']
        bbho_df = df[df['element_type'] == 'BeamBeamBiGaussian3D']
        bb_df = pd.concat([bblr_df, bbho_df])

        assert (len(bblr_df) == 2 * sum(
            [ip_bb_config[ip]['num_lr_per_side'] for ip in ip_bb_config.keys()]))
        assert (len(bbho_df) == len(ip_bb_config.keys()) * num_slices_head_on)

        # Check that beam-beam scale knob works correctly
        collider.vars['beambeam_scale'] = 1
        for nn in bb_df.name.values:
            assert collider[line_name][nn].scale_strength == 1
        collider.vars['beambeam_scale'] = 0
        for nn in bb_df.name.values:
            assert collider[line_name][nn].scale_strength == 0
        collider.vars['beambeam_scale'] = 1
        for nn in bb_df.name.values:
            assert collider[line_name][nn].scale_strength == 1

        # Twiss with and without bb
        collider.vars['beambeam_scale'] = 1
        tw_bb_on = collider[line_name].twiss()
        collider.vars['beambeam_scale'] = 0
        tw_bb_off = collider[line_name].twiss()
        collider.vars['beambeam_scale'] = 1

        assert np.isclose(tw_bb_off.qx, qx_no_bb[line_name], rtol=0, atol=1e-4)
        assert np.isclose(tw_bb_off.qy, qy_no_bb[line_name], rtol=0, atol=1e-4)

        # Check that there is a tune shift of the order of 1.5e-2
        assert np.isclose(tw_bb_on.qx, qx_no_bb[line_name] - 1.5e-2, rtol=0, atol=4e-3)
        assert np.isclose(tw_bb_on.qy, qy_no_bb[line_name] - 1.5e-2, rtol=0, atol=4e-3)

        # Check that there is no effect on the orbit
        np.allclose(tw_bb_on.x, tw_bb_off.x, atol=1e-10, rtol=0)
        np.allclose(tw_bb_on.y, tw_bb_off.y, atol=1e-10, rtol=0)

    for name_weak, ip in product(['lhcb1', 'lhcb2'], ['ip1', 'ip2', 'ip5', 'ip8']):

        print(f'\n--> Checking {name_weak} {ip}\n')

        ip_n = int(ip[2])
        num_lr_per_side = ip_bb_config[ip]['num_lr_per_side']
        name_strong = line_config[name_weak]['strong_beam']
        sorting = line_config[name_weak]['sorting']

        # The bb lenses are setup based on the twiss taken with the bb off
        print('Twiss(es) (with bb off)')
        with xt._temp_knobs(collider, knobs={'beambeam_scale': 0}):
            tw_weak = collider[name_weak].twiss()
            tw_strong = collider[name_strong].twiss().reverse()

        # Survey starting from ip
        print('Survey(s) (starting from ip)')
        survey_weak = collider[name_weak].survey(element0=f'ip{ip_n}')
        survey_strong = collider[name_strong].survey(
                                            element0=f'ip{ip_n}').reverse()
        beta0_strong = collider[name_strong].particle_ref.beta0[0]
        gamma0_strong = collider[name_strong].particle_ref.gamma0[0]

        bunch_spacing_ds = (tw_weak.circumference / harmonic_number
                            * bunch_spacing_buckets)

        # Check lr encounters
        for side in ['l', 'r']:
            for iele in range(num_lr_per_side):
                nn_weak = f'bb_lr.{side}{ip_n}b{name_weak[-1]}_{iele+1:02d}'
                nn_strong = f'bb_lr.{side}{ip_n}b{name_strong[-1]}_{iele+1:02d}'

                assert nn_weak in tw_weak.name
                assert nn_strong in tw_strong.name

                ee_weak = collider[name_weak][nn_weak]

                assert isinstance(ee_weak, xf.BeamBeamBiGaussian2D)

                expected_sigma_x = np.sqrt(tw_strong['betx', nn_strong]
                                        * nemitt_x/beta0_strong/gamma0_strong)
                expected_sigma_y = np.sqrt(tw_strong['bety', nn_strong]
                                        * nemitt_y/beta0_strong/gamma0_strong)

                # Beam sizes
                assert np.isclose(ee_weak.other_beam_Sigma_11, expected_sigma_x**2,
                                atol=0, rtol=1e-5)
                assert np.isclose(ee_weak.other_beam_Sigma_33, expected_sigma_y**2,
                                atol=0, rtol=1e-5)

                # Check no coupling
                assert ee_weak.other_beam_Sigma_13 == 0

                # Orbit
                assert np.isclose(ee_weak.ref_shift_x, tw_weak['x', nn_weak],
                                rtol=0, atol=1e-4 * expected_sigma_x)
                assert np.isclose(ee_weak.ref_shift_y, tw_weak['y', nn_weak],
                                    rtol=0, atol=1e-4 * expected_sigma_y)

                # Separation
                assert np.isclose(ee_weak.other_beam_shift_x,
                    tw_strong['x', nn_strong] - tw_weak['x', nn_weak]
                    + survey_strong['X', nn_strong] - survey_weak['X', nn_weak],
                    rtol=0, atol=5e-4 * expected_sigma_x)

                assert np.isclose(ee_weak.other_beam_shift_y,
                    tw_strong['y', nn_strong] - tw_weak['y', nn_weak]
                    + survey_strong['Y', nn_strong] - survey_weak['Y', nn_weak],
                    rtol=0, atol=5e-4 * expected_sigma_y)

                # s position
                assert np.isclose(tw_weak['s', nn_weak] - tw_weak['s', f'ip{ip_n}'],
                                bunch_spacing_ds/2 * (iele+1) * sorting[side],
                                rtol=0, atol=10e-6)

                # Check intensity
                assert np.isclose(ee_weak.other_beam_num_particles, num_particles,
                                atol=0, rtol=1e-8)

                # Other checks
                assert ee_weak.min_sigma_diff < 1e-9
                assert ee_weak.min_sigma_diff > 0

                assert ee_weak.scale_strength == 1
                assert ee_weak.other_beam_q0 == 1

        # Check head on encounters

        # Quick check on _get_z_centroids
        assert np.isclose(np.mean(_get_z_centroids(100000, 5.)**2), 5**2,
                                rtol=0, atol=5e-4)
        assert np.isclose(np.mean(_get_z_centroids(100000, 5.)), 0,
                                rtol=0, atol=1e-10)

        z_centroids = _get_z_centroids(num_slices_head_on, sigmaz)
        assert len(z_centroids) == num_slices_head_on
        assert num_slices_head_on % 2 == 1

        # Measure crabbing angle
        z_crab_test = 0.01 # This is the z for the reversed strong beam (e.g. b2 and not b4)
        with xt._temp_knobs(collider, knobs={'beambeam_scale': 0}):
            tw_z_crab_plus = collider[name_strong].twiss(
                zeta0=-(z_crab_test), # This is the z for the physical strong beam (e.g. b4 and not b2)
                method='4d',
                freeze_longitudinal=True).reverse()
            tw_z_crab_minus = collider[name_strong].twiss(
                zeta0= -(-z_crab_test), # This is the z for the physical strong beam (e.g. b4 and not b2)
                method='4d',
                freeze_longitudinal=True).reverse()
        phi_crab_x = -(
            (tw_z_crab_plus['x', f'ip{ip_n}'] - tw_z_crab_minus['x', f'ip{ip_n}'])
                / (2 * z_crab_test))
        phi_crab_y = -(
            (tw_z_crab_plus['y', f'ip{ip_n}'] - tw_z_crab_minus['y', f'ip{ip_n}'])
                / (2 * z_crab_test))

        for ii, zz in list(zip(range(-(num_slices_head_on - 1) // 2,
                            (num_slices_head_on - 1) // 2 + 1),
                        z_centroids)):

            if ii == 0:
                side = 'c'
            elif ii < 0:
                side = 'l' if sorting['l'] == -1 else 'r'
            else:
                side = 'r' if sorting['r'] == 1 else 'l'

            nn_weak = f'bb_ho.{side}{ip_n}b{name_weak[-1]}_{int(abs(ii)):02d}'
            nn_strong = f'bb_ho.{side}{ip_n}b{name_strong[-1]}_{int(abs(ii)):02d}'

            ee_weak = collider[name_weak][nn_weak]

            assert isinstance(ee_weak, xf.BeamBeamBiGaussian3D)
            assert ee_weak.num_slices_other_beam == 1
            assert ee_weak.slices_other_beam_zeta_center[0] == 0

            # s position
            expected_s = zz / 2
            assert np.isclose(tw_weak['s', nn_weak] - tw_weak['s', f'ip{ip_n}'],
                            expected_s, atol=10e-6, rtol=0)

            # Beam sizes
            expected_sigma_x = np.sqrt(tw_strong['betx', nn_strong]
                                    * nemitt_x/beta0_strong/gamma0_strong)
            expected_sigma_y = np.sqrt(tw_strong['bety', nn_strong]
                                    * nemitt_y/beta0_strong/gamma0_strong)

            assert np.isclose(ee_weak.slices_other_beam_Sigma_11[0],
                            expected_sigma_x**2,
                            atol=0, rtol=1e-5)
            assert np.isclose(ee_weak.slices_other_beam_Sigma_33[0],
                            expected_sigma_y**2,
                            atol=0, rtol=1e-5)

            expected_sigma_px = np.sqrt(tw_strong['gamx', nn_strong]
                                        * nemitt_x/beta0_strong/gamma0_strong)
            expected_sigma_py = np.sqrt(tw_strong['gamy', nn_strong]
                                        * nemitt_y/beta0_strong/gamma0_strong)
            assert np.isclose(ee_weak.slices_other_beam_Sigma_22[0],
                            expected_sigma_px**2,
                            atol=0, rtol=1e-4)
            assert np.isclose(ee_weak.slices_other_beam_Sigma_44[0],
                            expected_sigma_py**2,
                            atol=0, rtol=1e-4)

            expected_sigma_xpx = -(tw_strong['alfx', nn_strong]
                                    * nemitt_x / beta0_strong / gamma0_strong)
            expected_sigma_ypy = -(tw_strong['alfy', nn_strong]
                                    * nemitt_y / beta0_strong / gamma0_strong)
            assert np.isclose(ee_weak.slices_other_beam_Sigma_12[0],
                            expected_sigma_xpx,
                            atol=1e-12, rtol=5e-4)
            assert np.isclose(ee_weak.slices_other_beam_Sigma_34[0],
                            expected_sigma_ypy,
                            atol=1e-12, rtol=5e-4)

            # Assert no coupling
            assert ee_weak.slices_other_beam_Sigma_13[0] == 0
            assert ee_weak.slices_other_beam_Sigma_14[0] == 0
            assert ee_weak.slices_other_beam_Sigma_23[0] == 0
            assert ee_weak.slices_other_beam_Sigma_24[0] == 0

            # Orbit
            assert np.isclose(ee_weak.ref_shift_x, tw_weak['x', nn_weak],
                                rtol=0, atol=1e-4 * expected_sigma_x)
            assert np.isclose(ee_weak.ref_shift_px, tw_weak['px', nn_weak],
                                rtol=0, atol=1e-4 * expected_sigma_px)
            assert np.isclose(ee_weak.ref_shift_y, tw_weak['y', nn_weak],
                                rtol=0, atol=1e-4 * expected_sigma_y)
            assert np.isclose(ee_weak.ref_shift_py, tw_weak['py', nn_weak],
                                rtol=0, atol=1e-4 * expected_sigma_py)
            assert np.isclose(ee_weak.ref_shift_zeta, tw_weak['zeta', nn_weak],
                                rtol=0, atol=1e-9)
            assert np.isclose(ee_weak.ref_shift_pzeta,
                            tw_weak['ptau', nn_weak]/beta0_strong,
                            rtol=0, atol=1e-9)

            # Separation
            # for phi_crab definition, see Xsuite physics manual
            assert np.isclose(ee_weak.other_beam_shift_x,
                (tw_strong['x', nn_strong] - tw_weak['x', nn_weak]
                + survey_strong['X', nn_strong] - survey_weak['X', nn_weak]
                - phi_crab_x
                    * tw_strong.circumference / (2 * np.pi * harmonic_number)
                    * np.sin(2 * np.pi * zz
                            * harmonic_number / tw_strong.circumference)),
                rtol=0, atol=1e-6) # Not the cleanest, to be investigated

            assert np.isclose(ee_weak.other_beam_shift_y,
                (tw_strong['y', nn_strong] - tw_weak['y', nn_weak]
                + survey_strong['Y', nn_strong] - survey_weak['Y', nn_weak]
                - phi_crab_y
                    * tw_strong.circumference / (2 * np.pi * harmonic_number)
                    * np.sin(2 * np.pi * zz
                            * harmonic_number / tw_strong.circumference)),
                rtol=0, atol=1e-6) # Not the cleanest, to be investigated

            assert ee_weak.other_beam_shift_px == 0
            assert ee_weak.other_beam_shift_py == 0
            assert ee_weak.other_beam_shift_zeta == 0
            assert ee_weak.other_beam_shift_pzeta == 0

            # Check crossing angle
            # Assume that crossing is either in x or in y
            if np.abs(tw_weak['px', f'ip{ip_n}']) < 1e-6:
                # Vertical crossing
                assert np.isclose(ee_weak.alpha, np.pi/2, atol=5e-3, rtol=0)
                assert np.isclose(
                    2*ee_weak.phi,
                    tw_weak['py', f'ip{ip_n}'] - tw_strong['py', f'ip{ip_n}'],
                    atol=2e-7, rtol=0)
            else:
                # Horizontal crossing
                assert np.isclose(ee_weak.alpha,
                    (-15e-3 if ip_n==8 else 0)*{'lhcb1': 1, 'lhcb2': -1}[name_weak],
                    atol=5e-3, rtol=0)
                assert np.isclose(
                    2*ee_weak.phi,
                    tw_weak['px', f'ip{ip_n}'] - tw_strong['px', f'ip{ip_n}'],
                    atol=2e-7, rtol=0)

            # Check intensity
            assert np.isclose(ee_weak.slices_other_beam_num_particles[0],
                            num_particles/num_slices_head_on, atol=0, rtol=1e-8)

            # Other checks
            assert ee_weak.min_sigma_diff < 1e-9
            assert ee_weak.min_sigma_diff > 0

            assert ee_weak.threshold_singular < 1e-27
            assert ee_weak.threshold_singular > 0

            assert ee_weak._flag_beamstrahlung == 0

            assert ee_weak.scale_strength == 1
            assert ee_weak.other_beam_q0 == 1

            for nn in ['x', 'y', 'zeta', 'px', 'py', 'pzeta']:
                assert getattr(ee_weak, f'slices_other_beam_{nn}_center')[0] == 0


    # Check optics and orbit with bb off
    collider.vars['beambeam_scale'] = 0
    check_optics_orbit_etc(collider, line_names=['lhcb1', 'lhcb2'],
                           # From lumi leveling
                           sep_h_ip2=-0.00014330344100935583, # checked against normalized sep
                           sep_v_ip8=-3.441222062677253e-05, # checked against lumi
                           )

def test_stress_co_correction_and_lumi_leveling():

    collider = xt.Multiline.from_json('collider_hllhc14_02.json')
    collider.build_trackers()

    num_colliding_bunches = 2808
    num_particles_per_bunch = 1.15e11
    nemitt_x = 3.75e-6
    nemitt_y = 3.75e-6
    sigma_z = 0.0755
    beta0_b1 = collider.lhcb1.particle_ref.beta0[0]
    f_rev=1/(collider.lhcb1.get_length() /(beta0_b1 * clight))

    # Move to external vertical crossing
    collider.vars['phi_ir8'] = 90.

    tw_before_errors = collider.twiss(lines=['lhcb1', 'lhcb2'])

    # Add errors
    for line_name in ['lhcb1', 'lhcb2']:
        collider[line_name]['mqxb.a2r8..5'].knl[0] = 1e-5
        collider[line_name]['mqxb.a2l8..5'].knl[0] = -0.7e-5
        collider[line_name]['mqxb.a2r8..5'].ksl[0] = -1.3e-5
        collider[line_name]['mqxb.a2l8..5'].ksl[0] = 0.9e-5

        collider[line_name]['mqxb.a2r8..5'].knl[1] = collider[line_name]['mqxb.a2r8..4'].knl[1] * 1.3
        collider[line_name]['mqxb.a2l8..5'].knl[1] = collider[line_name]['mqxb.a2l8..4'].knl[1] * 1.3
    collider.lhcb1['mqy.a4l8.b1..1'].knl[1] = collider.lhcb1['mqy.a4l8.b1..2'].knl[1] * 0.7
    collider.lhcb1['mqy.a4r8.b1..1'].knl[1] = collider.lhcb1['mqy.a4r8.b1..2'].knl[1] * 1.2
    collider.lhcb2['mqy.a4l8.b2..1'].knl[1] = collider.lhcb2['mqy.a4l8.b2..2'].knl[1] * 1.1
    collider.lhcb2['mqy.a4r8.b2..1'].knl[1] = collider.lhcb2['mqy.a4r8.b2..2'].knl[1] * 1.1

    tw_after_errors = collider.twiss(lines=['lhcb1', 'lhcb2'])

    # Correct orbit
    for line_name in ['lhcb1', 'lhcb2']:
        xm.machine_tuning(line=collider[line_name],
            enable_closed_orbit_correction=True,
            enable_linear_coupling_correction=False,
            enable_tune_correction=False,
            enable_chromaticity_correction=False,
            knob_names=[],
            targets=None,
            line_co_ref=collider[line_name+'_co_ref'],
            co_corr_config=orbit_correction_config[line_name])

    tw_after_orbit_correction = collider.twiss(lines=['lhcb1', 'lhcb2'])

    print(f'Knobs before matching: on_sep8h = {collider.vars["on_sep8h"]._value} '
            f'on_sep8v = {collider.vars["on_sep8v"]._value}')

    # Correction assuming ideal behavior of the knobs
    knob_values_before_ideal_matching = {
        'on_sep8h': collider.vars['on_sep8h']._value,
        'on_sep8v': collider.vars['on_sep8v']._value,
    }

    # Lumi leveling assuming ideal behavior of the knobs
    collider.match(
        ele_start=['e.ds.l8.b1', 's.ds.r8.b2'],
        ele_stop=['s.ds.r8.b1', 'e.ds.l8.b2'],
        twiss_init='preserve',
        lines=['lhcb1', 'lhcb2'],
        vary=[
            # Knobs to control the separation
            xt.Vary('on_sep8h', step=1e-4),
            xt.Vary('on_sep8v', step=1e-4),
        ],
        targets=[
            xt.TargetLuminosity(ip_name='ip8',
                                    luminosity=2e14,
                                    tol=1e12,
                                    f_rev=1/(collider.lhcb1.get_length() /(beta0_b1 * clight)),
                                    num_colliding_bunches=num_colliding_bunches,
                                    num_particles_per_bunch=num_particles_per_bunch,
                                    nemitt_x=nemitt_x, nemitt_y=nemitt_y,
                                    sigma_z=sigma_z, crab=False),
            xt.TargetSeparationOrthogonalToCrossing(ip_name='ip8'),
        ],
    )

    tw_after_ideal_lumi_matching = collider.twiss(lines=['lhcb1', 'lhcb2'])

    # Reset knobs
    collider.vars['on_sep8h'] = knob_values_before_ideal_matching['on_sep8h']
    collider.vars['on_sep8v'] = knob_values_before_ideal_matching['on_sep8v']

    # Lumi leveling with orbit correction
    collider.match(
        lines=['lhcb1', 'lhcb2'],
        ele_start=['e.ds.l8.b1', 's.ds.r8.b2'],
        ele_stop=['s.ds.r8.b1', 'e.ds.l8.b2'],
        twiss_init='preserve',
        targets=[
            xt.TargetLuminosity(
                ip_name='ip8', luminosity=2e14, tol=1e12, f_rev=f_rev,
                num_colliding_bunches=num_colliding_bunches,
                num_particles_per_bunch=num_particles_per_bunch,
                nemitt_x=nemitt_x, nemitt_y=nemitt_y, sigma_z=sigma_z, crab=False),
            xt.TargetSeparationOrthogonalToCrossing(ip_name='ip8'),
            # Preserve crossing angle
            xt.TargetList(['px', 'py'], at='ip8', line='lhcb1', value='preserve', tol=1e-7, scale=1e3),
            xt.TargetList(['px', 'py'], at='ip8', line='lhcb2', value='preserve', tol=1e-7, scale=1e3),
            # Close the bumps
            xt.TargetList(['x', 'y'], at='s.ds.r8.b1', line='lhcb1', value='preserve', tol=1e-5, scale=1),
            xt.TargetList(['px', 'py'], at='s.ds.r8.b1', line='lhcb1', value='preserve', tol=1e-5, scale=1e3),
            xt.TargetList(['x', 'y'], at='e.ds.l8.b2', line='lhcb2', value='preserve', tol=1e-5, scale=1),
            xt.TargetList(['px', 'py'], at='e.ds.l8.b2', line='lhcb2', value='preserve', tol=1e-5, scale=1e3),
            ],
        vary=[
            xt.VaryList(['on_sep8h', 'on_sep8v'], step=1e-4), # to control separation
            xt.VaryList([
                # correctors to control the crossing angles
                'corr_co_acbyvs4.l8b1', 'corr_co_acbyhs4.l8b1',
                'corr_co_acbyvs4.r8b2', 'corr_co_acbyhs4.r8b2',
                # correctors to close the bumps
                'corr_co_acbyvs4.l8b2', 'corr_co_acbyhs4.l8b2',
                'corr_co_acbyvs4.r8b1', 'corr_co_acbyhs4.r8b1',
                'corr_co_acbcvs5.l8b2', 'corr_co_acbchs5.l8b2',
                'corr_co_acbyvs5.r8b1', 'corr_co_acbyhs5.r8b1'],
                step=1e-7),
        ],
    )

    print (f'Knobs after matching: on_sep8h = {collider.vars["on_sep8h"]._value} '
            f'on_sep8v = {collider.vars["on_sep8v"]._value}')

    tw_after_full_match = collider.twiss(lines=['lhcb1', 'lhcb2'])

    print(f'Before ideal matching: px = {tw_after_orbit_correction["lhcb1"]["px", "ip8"]:.3e} ')
    print(f'After ideal matching:  px = {tw_after_ideal_lumi_matching["lhcb1"]["px", "ip8"]:.3e} ')
    print(f'After full matching:   px = {tw_after_full_match["lhcb1"]["px", "ip8"]:.3e} ')
    print(f'Before ideal matching: py = {tw_after_orbit_correction["lhcb1"]["py", "ip8"]:.3e} ')
    print(f'After ideal matching:  py = {tw_after_ideal_lumi_matching["lhcb1"]["py", "ip8"]:.3e} ')
    print(f'After full matching:   py = {tw_after_full_match["lhcb1"]["py", "ip8"]:.3e} ')

    for place in ['ip1', 'ip8']:
        # Check that the errors are perturbing the crossing angles
        assert np.abs(tw_after_errors.lhcb1['px', place] - tw_before_errors.lhcb1['px', place]) > 10e-6
        assert np.abs(tw_after_errors.lhcb2['px', place] - tw_before_errors.lhcb2['px', place]) > 10e-6
        assert np.abs(tw_after_errors.lhcb1['py', place] - tw_before_errors.lhcb1['py', place]) > 10e-6
        assert np.abs(tw_after_errors.lhcb2['py', place] - tw_before_errors.lhcb2['py', place]) > 10e-6

        # Check that the orbit correction is restoring the crossing angles
        assert np.isclose(tw_after_orbit_correction.lhcb1['px', place],
                            tw_before_errors.lhcb1['px', place], atol=1e-6, rtol=0)
        assert np.isclose(tw_after_orbit_correction.lhcb2['px', place],
                            tw_before_errors.lhcb2['px', place], atol=1e-6, rtol=0)
        assert np.isclose(tw_after_orbit_correction.lhcb1['py', place],
                            tw_before_errors.lhcb1['py', place], atol=1e-6, rtol=0)
        assert np.isclose(tw_after_orbit_correction.lhcb2['py', place],
                            tw_before_errors.lhcb2['py', place], atol=1e-6, rtol=0)

        # Check that the ideal lumi matching is perturbing the crossing angles
        assert np.abs(tw_after_ideal_lumi_matching.lhcb1['px', place] - tw_before_errors.lhcb1['px', place]) > 1e-6
        assert np.abs(tw_after_ideal_lumi_matching.lhcb2['px', place] - tw_before_errors.lhcb2['px', place]) > 1e-6
        assert np.abs(tw_after_ideal_lumi_matching.lhcb1['py', place] - tw_before_errors.lhcb1['py', place]) > 1e-6
        assert np.abs(tw_after_ideal_lumi_matching.lhcb2['py', place] - tw_before_errors.lhcb2['py', place]) > 1e-6

        # Check that the full matching is preserving the crossing angles
        assert np.isclose(tw_after_full_match.lhcb1['px', place],
                            tw_before_errors.lhcb1['px', place], atol=1e-7, rtol=0)
        assert np.isclose(tw_after_full_match.lhcb2['px', place],
                            tw_before_errors.lhcb2['px', place], atol=1e-7, rtol=0)
        assert np.isclose(tw_after_full_match.lhcb1['py', place],
                            tw_before_errors.lhcb1['py', place], atol=1e-7, rtol=0)
        assert np.isclose(tw_after_full_match.lhcb2['py', place],
                            tw_before_errors.lhcb2['py', place], atol=1e-7, rtol=0)


    ll_after_match = xt.lumi.luminosity_from_twiss(
        n_colliding_bunches=num_colliding_bunches,
        num_particles_per_bunch=num_particles_per_bunch,
        ip_name='ip8',
        nemitt_x=nemitt_x,
        nemitt_y=nemitt_y,
        sigma_z=sigma_z,
        twiss_b1=tw_after_full_match['lhcb1'],
        twiss_b2=tw_after_full_match['lhcb2'],
        crab=False)

    assert np.isclose(ll_after_match, 2e14, rtol=1e-2, atol=0)

    # Check orthogonality
    tw_b1 = tw_after_full_match['lhcb1']
    tw_b4 = tw_after_full_match['lhcb2']
    tw_b2 = tw_b4.reverse()

    diff_px = tw_b1['px', 'ip8'] - tw_b2['px', 'ip8']
    diff_py = tw_b1['py', 'ip8'] - tw_b2['py', 'ip8']
    diff_x = tw_b1['x', 'ip8'] - tw_b2['x', 'ip8']
    diff_y = tw_b1['y', 'ip8'] - tw_b2['y', 'ip8']

    dpx_norm = diff_px / np.sqrt(diff_px**2 + diff_py**2)
    dpy_norm = diff_py / np.sqrt(diff_px**2 + diff_py**2)
    dx_norm = diff_x / np.sqrt(diff_x**2 + diff_py**2)
    dy_norm = diff_y / np.sqrt(diff_x**2 + diff_py**2)

    assert np.isclose(dpx_norm*dx_norm + dpy_norm*dy_norm, 0, atol=1e-6)

    # Match separation to 2 sigmas in IP2
    print(f'Knobs before matching: on_sep2 = {collider.vars["on_sep2"]._value}')
    collider.match(
        lines=['lhcb1', 'lhcb2'],
        ele_start=['e.ds.l2.b1', 's.ds.r2.b2'],
        ele_stop=['s.ds.r2.b1', 'e.ds.l2.b2'],
        twiss_init='preserve',
        targets=[
            xt.TargetSeparation(ip_name='ip2', separation_norm=3, plane='x', tol=1e-4,
                            nemitt_x=nemitt_x, nemitt_y=nemitt_y),
            # Preserve crossing angle
            xt.TargetList(['px', 'py'], at='ip2', line='lhcb1', value='preserve', tol=1e-7, scale=1e3),
            xt.TargetList(['px', 'py'], at='ip2', line='lhcb2', value='preserve', tol=1e-7, scale=1e3),
            # Close the bumps
            xt.TargetList(['x', 'y'], at='s.ds.r2.b1', line='lhcb1', value='preserve', tol=1e-5, scale=1),
            xt.TargetList(['px', 'py'], at='s.ds.r2.b1', line='lhcb1', value='preserve', tol=1e-5, scale=1e3),
            xt.TargetList(['x', 'y'], at='e.ds.l2.b2', line='lhcb2', value='preserve', tol=1e-5, scale=1),
            xt.TargetList(['px', 'py'], at='e.ds.l2.b2', line='lhcb2', value='preserve', tol=1e-5, scale=1e3),
        ],
        vary=
            [xt.Vary('on_sep2', step=1e-4),
            xt.VaryList([
                # correctors to control the crossing angles
                'corr_co_acbyvs4.l2b1', 'corr_co_acbyhs4.l2b1',
                'corr_co_acbyvs4.r2b2', 'corr_co_acbyhs4.r2b2',
                # correctors to close the bumps
                'corr_co_acbyvs4.l2b2', 'corr_co_acbyhs4.l2b2',
                'corr_co_acbyvs4.r2b1', 'corr_co_acbyhs4.r2b1',
                'corr_co_acbyhs5.l2b2', 'corr_co_acbyvs5.l2b2',
                'corr_co_acbchs5.r2b1', 'corr_co_acbcvs5.r2b1'],
                step=1e-7),
            ],
    )
    print(f'Knobs after matching: on_sep2 = {collider.vars["on_sep2"]._value}')

    tw_after_ip2_match = collider.twiss(lines=['lhcb1', 'lhcb2'])

    # Check normalized separation
    mean_betx = np.sqrt(tw_after_ip2_match['lhcb1']['betx', 'ip2']
                    *tw_after_ip2_match['lhcb2']['betx', 'ip2'])
    gamma0 = tw_after_ip2_match['lhcb1'].particle_on_co.gamma0[0]
    beta0 = tw_after_ip2_match['lhcb1'].particle_on_co.beta0[0]
    sigmax = np.sqrt(nemitt_x * mean_betx /gamma0 / beta0)

    assert np.isclose(collider.vars['on_sep2']._value/1000, 3*sigmax/2, rtol=1e-3, atol=0)


