#!/usr/bin/env python3

"""Unit tests for RXCROPMATURITY tests"""

import os
import sys
import pytest

# -- add CTSM root to path (needed to import from cime_config)
_CTSM_PYTHON = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, os.pardir)
_CTSM_ROOT = os.path.join(_CTSM_PYTHON, os.pardir)
sys.path.insert(1, _CTSM_PYTHON)
sys.path.insert(1, _CTSM_ROOT)

# pylint: disable=wrong-import-position
from ctsm import unit_testing
from cime_config.SystemTests.rxcropmaturity import (
    _copy_extra_files_from_run_to_baseline,
    _get_baseline_dir_with_files_from_run,
    _get_seasons_for_generate_gdds,
    BASELINE_SUBDIR_WITH_INPUTS,
    BASELINE_VERSION_OF_SCRIPT_INPUT_FILES,
)
from cime.CIME.utils import SharedArea

# Allow names that pylint doesn't like, because otherwise I find it hard
# to make readable unit test names
# pylint: disable=invalid-name
# pylint: disable=too-many-locals


def _create_sample_file(directory, filename, content):
    """Helper method to create a file with given content"""
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", encoding="utf8") as f:
        f.write(content)
    return filepath


@pytest.fixture(scope="session", autouse=True)
def _setup_ctsm_tests():
    """Initialize CTSM test environment once per test session."""
    unit_testing.setup_for_tests()


@pytest.fixture(name="gdd_env")
def fixture_gdd_env(tmp_path):
    """Provide directories and script name for gddgen-based tests."""
    gddgen_out_dir = tmp_path / "gddgen_out"
    baseline_dir = tmp_path / "baseline"
    gddgen_out_dir.mkdir()
    baseline_dir.mkdir()
    return {
        "gddgen_out_dir": str(gddgen_out_dir),
        "baseline_dir": str(baseline_dir),
        "which_script": "generate_gdds",
    }


@pytest.fixture(name="baseline_env")
def fixture_baseline_env(tmp_path):
    """Provide baseline/versioned dirs and script name for baseline-dir tests."""
    baseline_dir = os.path.join(str(tmp_path), "baseline")
    versioned_dir = os.path.join(baseline_dir, BASELINE_VERSION_OF_SCRIPT_INPUT_FILES)
    os.makedirs(versioned_dir)
    return {
        "baseline_dir": baseline_dir,
        "versioned_dir": versioned_dir,
        "which_script": "generate_gdds",
    }


class TestCopyFilesFromGddgenRunToBaseline:
    """Tests of _copy_files_from_gddgen_run_to_baseline()"""

    def _create_h1_h2_files(self, gddgen_out_dir):
        """Helper method to create sample h1i and h2i files"""
        h1_file = _create_sample_file(
            gddgen_out_dir, "test.clm2.h1i.2000-01-01.nc", "h1 file content"
        )
        h2_file = _create_sample_file(
            gddgen_out_dir, "test.clm2.h2i.2000-01-01.nc", "h2 file content"
        )
        return [h1_file, h2_file]

    def test_basic_copy_functionality(self, gdd_env):
        """Test that h1 and h2 files are copied to baseline subdirectory"""
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        baseline_dir = gdd_env["baseline_dir"]
        which_script = gdd_env["which_script"]

        expected_files = self._create_h1_h2_files(gddgen_out_dir)
        # Also create an h1a file that should NOT be copied
        h1a_filename = "test.clm2.h1a.2000-01-01.nc"
        _create_sample_file(gddgen_out_dir, h1a_filename, "h1a file content")

        _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, baseline_dir)

        # Check that subdirectory was created
        baseline_subdir = os.path.join(baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script)
        assert os.path.exists(baseline_subdir)

        # Check that h1 and h2 files were copied
        for orig_file in expected_files:
            target_file = os.path.join(baseline_subdir, os.path.basename(orig_file))
            assert os.path.exists(target_file)

            # Verify content was copied correctly
            with open(orig_file, "r", encoding="utf8") as f:
                orig_content = f.read()
            with open(target_file, "r", encoding="utf8") as f:
                target_content = f.read()
            assert orig_content == target_content

        # Check that h1a file was NOT copied
        h1a_file = os.path.join(baseline_subdir, h1a_filename)
        assert not os.path.exists(h1a_file)

    def test_basic_copy_functionality_checkrxboth(self, gdd_env):
        """Test that which_script='check_rxboth_run' copies expected files"""
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        baseline_dir = gdd_env["baseline_dir"]
        which_script = "check_rxboth_run"

        # Only h1i files are expected for check_rxboth_run
        expected_files = [
            _create_sample_file(gddgen_out_dir, "test.clm2.h1i.2000-01-01.nc", "h1 file 1 content"),
            _create_sample_file(gddgen_out_dir, "test.clm2.h1i.2000-01-02.nc", "h1 file 2 content"),
        ]

        _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, baseline_dir)

        # Verify baseline subdir exists
        baseline_subdir = os.path.join(baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script)
        assert os.path.exists(baseline_subdir)

        # Verify expected files are present and contents match
        for orig_file in expected_files:
            target_file = os.path.join(baseline_subdir, os.path.basename(orig_file))
            assert os.path.exists(target_file)
            with open(orig_file, "r", encoding="utf8") as f:
                orig_content = f.read()
            with open(target_file, "r", encoding="utf8") as f:
                target_content = f.read()
            assert orig_content == target_content

    def test_error_invalid_whichscript(self, gdd_env):
        """Test that error is thrown on unrecognized which_script"""
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        baseline_dir = gdd_env["baseline_dir"]
        which_script = "jsdnfwoeurn3oi4n3"

        with pytest.raises(ValueError, match=f"Unrecognized.*{which_script}"):
            _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, baseline_dir)

    def test_symlink_when_file_exists_in_baseline(self, gdd_env):
        """Test that symlinks are created when files already exist in baseline_dir"""
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        baseline_dir = gdd_env["baseline_dir"]
        which_script = gdd_env["which_script"]

        # Create h1 file in gddgen_out_dir
        filename = "test.clm2.h1i.2000-01-01.nc"
        file_content = "h1 file content"
        baseline_content = "existing baseline file content"

        _create_sample_file(gddgen_out_dir, filename, file_content)

        # Create the same file in baseline_dir (top level)
        existing_file = _create_sample_file(baseline_dir, filename, baseline_content)

        _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, baseline_dir)

        # Check that a symlink was created in the subdirectory
        baseline_subdir = os.path.join(baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script)
        target_file = os.path.join(baseline_subdir, filename)

        assert os.path.islink(target_file)
        assert os.path.realpath(target_file) == existing_file

        # Verify symlink points to the existing file, not the gddgen file
        with open(target_file, "r", encoding="utf8") as f:
            content = f.read()
        assert content == baseline_content

    def test_mixed_copy_and_symlink(self, gdd_env):
        """Test that some files are copied and others are symlinked"""
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        baseline_dir = gdd_env["baseline_dir"]
        which_script = gdd_env["which_script"]

        # Create two h1 files in gddgen_out_dir
        filename1 = "test.clm2.h1i.2000-01-01.nc"
        filename2 = "test.clm2.h1i.2000-01-02.nc"
        content1 = "h1 file 1 content"
        content2 = "h1 file 2 content"
        baseline_content = "existing baseline file content"

        _create_sample_file(gddgen_out_dir, filename1, content1)
        _create_sample_file(gddgen_out_dir, filename2, content2)

        # Create only the first file in baseline_dir
        _create_sample_file(baseline_dir, filename1, baseline_content)

        _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, baseline_dir)

        baseline_subdir = os.path.join(baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script)
        target_file1 = os.path.join(baseline_subdir, filename1)
        target_file2 = os.path.join(baseline_subdir, filename2)

        # First file should be a symlink pointing to the real file in directory above
        assert os.path.islink(target_file1)
        assert os.path.realpath(target_file1) == os.path.join(baseline_dir, filename1)

        # Second file should be a regular file (copied)
        assert not os.path.islink(target_file2)
        with open(target_file2, "r", encoding="utf8") as f:
            content = f.read()
        assert content == content2

    def test_error_when_gddgen_out_dir_missing(self, gdd_env):
        """Test that FileNotFoundError is raised when gddgen_out_dir doesn't exist"""
        baseline_dir = gdd_env["baseline_dir"]
        which_script = gdd_env["which_script"]
        nonexistent_dir = "/path/that/does/not/exist"

        with pytest.raises(FileNotFoundError) as exc_info:
            _copy_extra_files_from_run_to_baseline(which_script, nonexistent_dir, baseline_dir)

        assert str(exc_info.value).endswith(nonexistent_dir)

    def test_error_when_baseline_dir_missing(self, gdd_env):
        """Test that FileNotFoundError is raised when baseline_dir doesn't exist"""
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        which_script = gdd_env["which_script"]
        nonexistent_dir = "/path/that/does/not/exist"

        with pytest.raises(FileNotFoundError) as exc_info:
            _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, nonexistent_dir)

        assert str(exc_info.value).endswith(nonexistent_dir)

    def test_error_when_no_h1_h2_files_found(self, gdd_env):
        """Test that FileNotFoundError is raised when no h1/h2 files are found"""
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        baseline_dir = gdd_env["baseline_dir"]
        which_script = gdd_env["which_script"]

        # Create only h1a file (should not match pattern)
        h1a_filename = "test.clm2.h1a.2000-01-01.nc"
        _create_sample_file(gddgen_out_dir, h1a_filename, "h1a file content")

        with pytest.raises(FileNotFoundError) as exc_info:
            _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, baseline_dir)

        # Check that error message contains the pattern
        error_msg = str(exc_info.value)
        assert "No files found matching pattern" in error_msg
        assert "*clm2.h[12]i*.nc" in error_msg

    def test_multiple_h1_and_h2_files(self, gdd_env):
        """Test that multiple h1 and h2 files are all copied"""
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        baseline_dir = gdd_env["baseline_dir"]
        which_script = gdd_env["which_script"]

        # Create multiple h1 and h2 files
        files_to_create = [
            "test.clm2.h1i.2000-01-01.nc",
            "test.clm2.h1i.2000-01-02.nc",
            "test.clm2.h2i.2000-01-01.nc",
            "test.clm2.h2i.2000-01-02.nc",
            "test.clm2.h1i.2001-01-01.nc",
        ]

        for filename in files_to_create:
            _create_sample_file(gddgen_out_dir, filename, f"content of {filename}")

        _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, baseline_dir)

        baseline_subdir = os.path.join(baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script)

        # Check that all files were copied
        for filename in files_to_create:
            target_file = os.path.join(baseline_subdir, filename)
            assert os.path.exists(target_file)

    def test_file_permissions_with_shared_area(self, gdd_env):
        """
        Test that files copied have standard read-only permissions (0o644) set explicitly via
        os.chmod, and that directories created within SharedArea context have group-writable
        permissions (0o775) from the umask.
        """
        gddgen_out_dir = gdd_env["gddgen_out_dir"]
        baseline_dir = gdd_env["baseline_dir"]
        which_script = gdd_env["which_script"]
        filename = "test.clm2.h1i.2000-01-01.nc"

        # Create h1 file outside of SharedArea context with restrictive permissions
        orig_file = _create_sample_file(gddgen_out_dir, filename, "test content")
        # Set restrictive permissions on source file (no group write)
        os.chmod(orig_file, 0o600)

        # Verify the original file does NOT have group-read permissions
        orig_stat = os.stat(orig_file)
        orig_mode = orig_stat.st_mode
        # Check if group-read bit (0o040) is set in the file mode
        assert not (orig_mode & 0o040), "Original file should not be group-readable before copy"

        with SharedArea():
            _copy_extra_files_from_run_to_baseline(which_script, gddgen_out_dir, baseline_dir)

        baseline_subdir = os.path.join(baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script)
        target_file = os.path.join(baseline_subdir, filename)

        # Check that the copied file has standard permissions (0o644 = rw-r--r--)
        # This is set explicitly via os.chmod in the function
        file_stat = os.stat(target_file)
        file_mode = file_stat.st_mode
        assert (
            file_mode & 0o777
        ) == 0o644, "Copied file should have exactly 0o644 (rw-r--r--) permissions"

        # Verify the subdirectory is all-readable but only owner-writable (0o755)
        subdir_stat = os.stat(baseline_subdir)
        subdir_mode = subdir_stat.st_mode
        assert (
            subdir_mode & 0o777
        ) == 0o755, "Subdirectory should have exactly 0o755 (rwxr-xr-x) permissions"

        # Verify original file permissions haven't changed
        orig_stat_after = os.stat(orig_file)
        assert (
            orig_mode == orig_stat_after.st_mode
        ), "Original file permissions should not have changed"


class TestGetBaselineDirWithFilesFromGddgenRun:
    """Tests of _get_baseline_dir_with_files_from_run()"""

    def _create_test_case(self, versioned_dir, which_script, case_name, resolution):
        """Helper to create a test case directory with lnd_in file"""
        case_dir = os.path.join(versioned_dir, case_name)
        inputs_dir = os.path.join(case_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script)
        casedocs_dir = os.path.join(case_dir, "CaseDocs")
        os.makedirs(inputs_dir)
        os.makedirs(casedocs_dir)

        # Create lnd_in file with resolution info
        lnd_in_content = (
            f"some content\n!#     /path/... -res {resolution} -mask gx3v7\nmore content\n"
        )
        _create_sample_file(casedocs_dir, "lnd_in", lnd_in_content)

        return inputs_dir

    def test_finds_matching_resolution(self, baseline_env):
        """Test that function finds directory with matching resolution"""
        baseline_dir = baseline_env["baseline_dir"]
        versioned_dir = baseline_env["versioned_dir"]
        which_script = baseline_env["which_script"]
        target_res = "f09_g17"

        # Create test cases with different resolutions
        self._create_test_case(versioned_dir, which_script, "test_case_f19", "f19_g17")
        expected_dir = self._create_test_case(
            versioned_dir, which_script, "test_case_f09", target_res
        )
        self._create_test_case(versioned_dir, which_script, "test_case_f10", "f10_f10_mg37")

        result = _get_baseline_dir_with_files_from_run(which_script, baseline_dir, target_res)

        assert result == expected_dir

    def test_error_when_no_baseline_subdirs_exist(self, baseline_env):
        """Test FileNotFoundError when no baseline subdirectories exist"""
        baseline_dir = baseline_env["baseline_dir"]
        versioned_dir = baseline_env["versioned_dir"]
        which_script = baseline_env["which_script"]
        target_res = "f09_g17"

        # Create a case directory but without the BASELINE_SUBDIR_WITH_INPUTS subdirectory
        case_dir = os.path.join(versioned_dir, "test_case")
        os.makedirs(case_dir)

        with pytest.raises(FileNotFoundError) as exc_info:
            _get_baseline_dir_with_files_from_run(which_script, baseline_dir, target_res)

        # Check that error message contains the expected pattern
        expected_pattern = os.path.join(
            versioned_dir, "*", BASELINE_SUBDIR_WITH_INPUTS, which_script
        )
        assert expected_pattern in str(exc_info.value)

    def test_error_when_no_matching_resolution(self, baseline_env):
        """Test FileNotFoundError when no case matches the resolution"""
        baseline_dir = baseline_env["baseline_dir"]
        versioned_dir = baseline_env["versioned_dir"]
        which_script = baseline_env["which_script"]
        target_res = "f09_g17"

        # Create test cases with different resolutions
        self._create_test_case(versioned_dir, which_script, "test_case_f19", "f19_g17")
        self._create_test_case(versioned_dir, which_script, "test_case_f10", "f10_f10_mg37")

        with pytest.raises(FileNotFoundError) as exc_info:
            _get_baseline_dir_with_files_from_run(which_script, baseline_dir, target_res)

        error_msg = str(exc_info.value)
        assert "No tests found" in error_msg
        assert target_res in error_msg
        assert str(versioned_dir) in error_msg

    def test_error_when_multiple_matches_in_single_lnd_in(self, baseline_env):
        """Test RuntimeError when lnd_in has multiple resolution matches"""
        baseline_dir = baseline_env["baseline_dir"]
        versioned_dir = baseline_env["versioned_dir"]
        which_script = baseline_env["which_script"]
        target_res = "f09_g17"

        # Create case with lnd_in containing multiple matches
        case_dir = os.path.join(versioned_dir, "test_case")
        inputs_dir = os.path.join(case_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script)
        casedocs_dir = os.path.join(case_dir, "CaseDocs")
        os.makedirs(inputs_dir)
        os.makedirs(casedocs_dir)

        # Create lnd_in with duplicate resolution entries
        lnd_in_content = f"config line 1\n-res {target_res}\nconfig line 2\n-res {target_res}\n"
        _create_sample_file(casedocs_dir, "lnd_in", lnd_in_content)

        with pytest.raises(RuntimeError) as exc_info:
            _get_baseline_dir_with_files_from_run(which_script, baseline_dir, target_res)

        error_msg = str(exc_info.value)
        assert "Expected at most 1 match" in error_msg
        assert target_res in error_msg
        assert "got 2" in error_msg

    def test_handles_special_characters_in_resolution(self, baseline_env):
        """Test that function properly escapes special regex characters in resolution"""
        baseline_dir = baseline_env["baseline_dir"]
        versioned_dir = baseline_env["versioned_dir"]
        which_script = baseline_env["which_script"]
        # Use resolution with actual regex special characters that are safe for filenames
        target_res = "f^09.g17+]test"

        expected_dir = self._create_test_case(versioned_dir, which_script, "test_case", target_res)

        result = _get_baseline_dir_with_files_from_run(which_script, baseline_dir, target_res)

        assert result == expected_dir

    def test_resolution_must_match_exactly(self, baseline_env):
        """Test that resolution matching is exact (not substring)"""
        baseline_dir = baseline_env["baseline_dir"]
        versioned_dir = baseline_env["versioned_dir"]
        which_script = baseline_env["which_script"]
        target_res = "f09"

        # Create case with resolution that contains target as substring
        self._create_test_case(versioned_dir, which_script, "test_case", "f09_g17")

        # Should not match because we're looking for exact "-res f09", not "-res f09_g17"
        with pytest.raises(FileNotFoundError):
            _get_baseline_dir_with_files_from_run(which_script, baseline_dir, target_res)


class TestGetSeasonsForGenerateGdds:
    """Tests of _get_seasons_for_generate_gdds()"""

    @pytest.mark.parametrize("run_startyear, run_nyears", [(1850, 31), (1850, 5), (1850, 4)])
    def test_get_seasons_for_generate_gdds_valid(self, run_startyear, run_nyears):
        """Make sure it doesn't fail with a valid setup"""
        _get_seasons_for_generate_gdds(run_startyear, run_nyears)

    @pytest.mark.parametrize("run_startyear, run_nyears", [(1850, 3), (1850, -1), (2000, 0)])
    def test_get_seasons_for_generate_gdds_invalid(self, run_startyear, run_nyears):
        """Make sure it does fail with an invalid setup"""
        with pytest.raises(ValueError, match="run_nyears < minimum"):
            _get_seasons_for_generate_gdds(run_startyear, run_nyears)
