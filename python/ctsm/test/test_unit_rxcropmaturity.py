#!/usr/bin/env python3

"""Unit tests for RXCROPMATURITY tests"""

import tempfile
import shutil
import unittest
import os
import sys

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
    BASELINE_SUBDIR_WITH_INPUTS,
    BASELINE_VERSION_OF_SCRIPT_INPUT_FILES,
)
from cime.CIME.utils import SharedArea

# Allow names that pylint doesn't like, because otherwise I find it hard
# to make readable unit test names
# pylint: disable=invalid-name


def _create_sample_file(directory, filename, content):
    """Helper method to create a file with given content"""
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", encoding="utf8") as f:
        f.write(content)
    return filepath


class TestCopyFilesFromGddgenRunToBaseline(unittest.TestCase):
    """Tests of _copy_files_from_gddgen_run_to_baseline()"""

    def setUp(self):
        """Create temporary directories for testing"""
        self.temp_base = tempfile.mkdtemp()
        self.gddgen_out_dir = os.path.join(self.temp_base, "gddgen_out")
        self.baseline_dir = os.path.join(self.temp_base, "baseline")
        os.makedirs(self.gddgen_out_dir)
        os.makedirs(self.baseline_dir)
        self._which_script = "generate_gdds"

    def tearDown(self):
        """Clean up temporary directories"""
        if os.path.exists(self.temp_base):
            shutil.rmtree(self.temp_base)

    def _create_h1_h2_files(self):
        """Helper method to create sample h1i and h2i files"""
        h1_file = _create_sample_file(
            self.gddgen_out_dir, "test.clm2.h1i.2000-01-01.nc", "h1 file content"
        )
        h2_file = _create_sample_file(
            self.gddgen_out_dir, "test.clm2.h2i.2000-01-01.nc", "h2 file content"
        )
        return [h1_file, h2_file]

    def test_basic_copy_functionality(self):
        """Test that h1 and h2 files are copied to baseline subdirectory"""
        expected_files = self._create_h1_h2_files()
        # Also create an h1a file that should NOT be copied
        h1a_filename = "test.clm2.h1a.2000-01-01.nc"
        _create_sample_file(self.gddgen_out_dir, h1a_filename, "h1a file content")

        _copy_extra_files_from_run_to_baseline(
            self._which_script, self.gddgen_out_dir, self.baseline_dir
        )

        # Check that subdirectory was created
        baseline_subdir = os.path.join(
            self.baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, self._which_script
        )
        self.assertTrue(os.path.exists(baseline_subdir))

        # Check that h1 and h2 files were copied
        for orig_file in expected_files:
            target_file = os.path.join(baseline_subdir, os.path.basename(orig_file))
            self.assertTrue(os.path.exists(target_file))

            # Verify content was copied correctly
            with open(orig_file, "r", encoding="utf8") as f:
                orig_content = f.read()
            with open(target_file, "r", encoding="utf8") as f:
                target_content = f.read()
            self.assertEqual(orig_content, target_content)

        # Check that h1a file was NOT copied
        h1a_file = os.path.join(baseline_subdir, h1a_filename)
        self.assertFalse(os.path.exists(h1a_file))

    def test_basic_copy_functionality_checkrxboth(self):
        """Test that which_script='check_rxboth_run' doesn't fail"""
        expected_files = self._create_h1_h2_files()

        _copy_extra_files_from_run_to_baseline(
            "check_rxboth_run", self.gddgen_out_dir, self.baseline_dir
        )

    def test_error_invalid_whichscript(self):
        """Test that error is thrown on unrecognized which_script"""
        which_script = "jsdnfwoeurn3oi4n3"

        with self.assertRaisesRegex(ValueError, f"Unrecognized.*{which_script}"):
            _copy_extra_files_from_run_to_baseline(
                which_script, self.gddgen_out_dir, self.baseline_dir
            )

    def test_symlink_when_file_exists_in_baseline(self):
        """Test that symlinks are created when files already exist in baseline_dir"""
        # Create h1 file in gddgen_out_dir
        filename = "test.clm2.h1i.2000-01-01.nc"
        file_content = "h1 file content"
        baseline_content = "existing baseline file content"

        _create_sample_file(self.gddgen_out_dir, filename, file_content)

        # Create the same file in baseline_dir (top level)
        existing_file = _create_sample_file(self.baseline_dir, filename, baseline_content)

        _copy_extra_files_from_run_to_baseline(
            self._which_script, self.gddgen_out_dir, self.baseline_dir
        )

        # Check that a symlink was created in the subdirectory
        baseline_subdir = os.path.join(
            self.baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, self._which_script
        )
        target_file = os.path.join(baseline_subdir, filename)

        self.assertTrue(os.path.islink(target_file))
        self.assertEqual(os.path.realpath(target_file), existing_file)

        # Verify symlink points to the existing file, not the gddgen file
        with open(target_file, "r", encoding="utf8") as f:
            content = f.read()
        self.assertEqual(content, baseline_content)

    def test_mixed_copy_and_symlink(self):
        """Test that some files are copied and others are symlinked"""
        # Create two h1 files in gddgen_out_dir
        filename1 = "test.clm2.h1i.2000-01-01.nc"
        filename2 = "test.clm2.h1i.2000-01-02.nc"
        content1 = "h1 file 1 content"
        content2 = "h1 file 2 content"
        baseline_content = "existing baseline file content"

        _create_sample_file(self.gddgen_out_dir, filename1, content1)
        _create_sample_file(self.gddgen_out_dir, filename2, content2)

        # Create only the first file in baseline_dir
        _create_sample_file(self.baseline_dir, filename1, baseline_content)

        _copy_extra_files_from_run_to_baseline(
            self._which_script, self.gddgen_out_dir, self.baseline_dir
        )

        baseline_subdir = os.path.join(
            self.baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, self._which_script
        )
        target_file1 = os.path.join(baseline_subdir, filename1)
        target_file2 = os.path.join(baseline_subdir, filename2)

        # First file should be a symlink pointing to the real file in directory above
        self.assertTrue(os.path.islink(target_file1))
        self.assertEqual(os.path.realpath(target_file1), os.path.join(self.baseline_dir, filename1))

        # Second file should be a regular file (copied)
        self.assertFalse(os.path.islink(target_file2))
        with open(target_file2, "r", encoding="utf8") as f:
            content = f.read()
        self.assertEqual(content, content2)

    def test_error_when_gddgen_out_dir_missing(self):
        """Test that FileNotFoundError is raised when gddgen_out_dir doesn't exist"""
        nonexistent_dir = "/path/that/does/not/exist"

        with self.assertRaises(FileNotFoundError) as context:
            _copy_extra_files_from_run_to_baseline(
                self._which_script, nonexistent_dir, self.baseline_dir
            )

        self.assertEqual(str(context.exception), nonexistent_dir)

    def test_error_when_baseline_dir_missing(self):
        """Test that FileNotFoundError is raised when baseline_dir doesn't exist"""
        nonexistent_dir = "/path/that/does/not/exist"

        with self.assertRaises(FileNotFoundError) as context:
            _copy_extra_files_from_run_to_baseline(
                self._which_script, self.gddgen_out_dir, nonexistent_dir
            )

        self.assertEqual(str(context.exception), nonexistent_dir)

    def test_error_when_no_h1_h2_files_found(self):
        """Test that FileNotFoundError is raised when no h1/h2 files are found"""
        # Create only h1a file (should not match pattern)
        h1a_filename = "test.clm2.h1a.2000-01-01.nc"
        _create_sample_file(self.gddgen_out_dir, h1a_filename, "h1a file content")

        with self.assertRaises(FileNotFoundError) as context:
            _copy_extra_files_from_run_to_baseline(
                self._which_script, self.gddgen_out_dir, self.baseline_dir
            )

        # Check that error message contains the pattern
        error_msg = str(context.exception)
        self.assertIn("No files found matching pattern", error_msg)
        self.assertIn("*clm2.h[12]i*.nc", error_msg)

    def test_multiple_h1_and_h2_files(self):
        """Test that multiple h1 and h2 files are all copied"""
        # Create multiple h1 and h2 files
        files_to_create = [
            "test.clm2.h1i.2000-01-01.nc",
            "test.clm2.h1i.2000-01-02.nc",
            "test.clm2.h2i.2000-01-01.nc",
            "test.clm2.h2i.2000-01-02.nc",
            "test.clm2.h1i.2001-01-01.nc",
        ]

        for filename in files_to_create:
            _create_sample_file(self.gddgen_out_dir, filename, f"content of {filename}")

        _copy_extra_files_from_run_to_baseline(
            self._which_script, self.gddgen_out_dir, self.baseline_dir
        )

        baseline_subdir = os.path.join(
            self.baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, self._which_script
        )

        # Check that all files were copied
        for filename in files_to_create:
            target_file = os.path.join(baseline_subdir, filename)
            self.assertTrue(os.path.exists(target_file))

    def test_file_permissions_with_shared_area(self):
        """
        Test that files copied have standard read-only permissions (0o644) set explicitly via
        os.chmod, and that directories created within SharedArea context have group-writable
        permissions (0o775) from the umask.
        """
        filename = "test.clm2.h1i.2000-01-01.nc"

        # Create h1 file outside of SharedArea context with restrictive permissions
        orig_file = _create_sample_file(self.gddgen_out_dir, filename, "test content")
        # Set restrictive permissions on source file (no group write)
        os.chmod(orig_file, 0o600)

        # Verify the original file does NOT have group-read permissions
        orig_stat = os.stat(orig_file)
        orig_mode = orig_stat.st_mode
        # Check if group-read bit (0o040) is set in the file mode
        self.assertFalse(
            orig_mode & 0o040,
            "Original file should not be group-readable before copy",
        )

        with SharedArea():
            _copy_extra_files_from_run_to_baseline(
                self._which_script, self.gddgen_out_dir, self.baseline_dir
            )

        baseline_subdir = os.path.join(
            self.baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, self._which_script
        )
        target_file = os.path.join(baseline_subdir, filename)

        # Check that the copied file has standard permissions (0o644 = rw-r--r--)
        # This is set explicitly via os.chmod in the function
        file_stat = os.stat(target_file)
        file_mode = file_stat.st_mode
        self.assertEqual(
            file_mode & 0o777,
            0o644,
            "Copied file should have exactly 0o644 (rw-r--r--) permissions",
        )

        # Verify the subdirectory is all-readable but only owner-writable (0o755)
        subdir_stat = os.stat(baseline_subdir)
        subdir_mode = subdir_stat.st_mode
        self.assertEqual(
            subdir_mode & 0o777,
            0o755,
            "Subdirectory should have exactly 0o755 (rwxr-xr-x) permissions",
        )

        # Verify original file permissions haven't changed
        orig_stat_after = os.stat(orig_file)
        self.assertEqual(
            orig_mode,
            orig_stat_after.st_mode,
            "Original file permissions should not have changed",
        )


class TestGetBaselineDirWithFilesFromGddgenRun(unittest.TestCase):
    """Tests of _get_baseline_dir_with_files_from_gddgen_run()"""

    def setUp(self):
        """Create temporary baseline directory structure for testing"""
        self.temp_base = tempfile.mkdtemp()
        self.baseline_dir = os.path.join(self.temp_base, "baseline")
        self.versioned_dir = os.path.join(self.baseline_dir, BASELINE_VERSION_OF_SCRIPT_INPUT_FILES)
        os.makedirs(self.versioned_dir)
        self._which_script = "generate_gdds"

    def tearDown(self):
        """Clean up temporary directories"""
        if os.path.exists(self.temp_base):
            shutil.rmtree(self.temp_base)

    def _create_test_case(self, case_name, resolution):
        """Helper to create a test case directory with lnd_in file"""
        case_dir = os.path.join(self.versioned_dir, case_name)
        inputs_dir = os.path.join(case_dir, BASELINE_SUBDIR_WITH_INPUTS, self._which_script)
        casedocs_dir = os.path.join(case_dir, "CaseDocs")
        os.makedirs(inputs_dir)
        os.makedirs(casedocs_dir)

        # Create lnd_in file with resolution info
        lnd_in_content = (
            f"some content\n!#     /path/... -res {resolution} -mask gx3v7\nmore content\n"
        )
        _create_sample_file(casedocs_dir, "lnd_in", lnd_in_content)

        return inputs_dir

    def test_finds_matching_resolution(self):
        """Test that function finds directory with matching resolution"""
        target_res = "f09_g17"

        # Create test cases with different resolutions
        self._create_test_case("test_case_f19", "f19_g17")
        expected_dir = self._create_test_case("test_case_f09", target_res)
        self._create_test_case("test_case_f10", "f10_f10_mg37")

        result = _get_baseline_dir_with_files_from_run(
            self._which_script, self.baseline_dir, target_res
        )

        self.assertEqual(result, expected_dir)

    def test_error_when_no_baseline_subdirs_exist(self):
        """Test FileNotFoundError when no baseline subdirectories exist"""
        target_res = "f09_g17"

        # Create a case directory but without the BASELINE_SUBDIR_WITH_INPUTS subdirectory
        case_dir = os.path.join(self.versioned_dir, "test_case")
        os.makedirs(case_dir)

        with self.assertRaises(FileNotFoundError) as context:
            _get_baseline_dir_with_files_from_run(self._which_script, self.baseline_dir, target_res)

        # Check that error message contains the expected pattern
        expected_pattern = os.path.join(
            self.versioned_dir, "*", BASELINE_SUBDIR_WITH_INPUTS, self._which_script
        )
        self.assertIn(expected_pattern, str(context.exception))

    def test_error_when_no_matching_resolution(self):
        """Test FileNotFoundError when no case matches the resolution"""
        target_res = "f09_g17"

        # Create test cases with different resolutions
        self._create_test_case("test_case_f19", "f19_g17")
        self._create_test_case("test_case_f10", "f10_f10_mg37")

        with self.assertRaises(FileNotFoundError) as context:
            _get_baseline_dir_with_files_from_run(self._which_script, self.baseline_dir, target_res)

        error_msg = str(context.exception)
        self.assertIn("No tests found", error_msg)
        self.assertIn(target_res, error_msg)
        self.assertIn(str(self.versioned_dir), error_msg)

    def test_error_when_multiple_matches_in_single_lnd_in(self):
        """Test RuntimeError when lnd_in has multiple resolution matches"""
        target_res = "f09_g17"

        # Create case with lnd_in containing multiple matches
        case_dir = os.path.join(self.versioned_dir, "test_case")
        inputs_dir = os.path.join(case_dir, BASELINE_SUBDIR_WITH_INPUTS, self._which_script)
        casedocs_dir = os.path.join(case_dir, "CaseDocs")
        os.makedirs(inputs_dir)
        os.makedirs(casedocs_dir)

        # Create lnd_in with duplicate resolution entries
        lnd_in_content = f"config line 1\n-res {target_res}\nconfig line 2\n-res {target_res}\n"
        _create_sample_file(casedocs_dir, "lnd_in", lnd_in_content)

        with self.assertRaises(RuntimeError) as context:
            _get_baseline_dir_with_files_from_run(self._which_script, self.baseline_dir, target_res)

        error_msg = str(context.exception)
        self.assertIn("Expected at most 1 match", error_msg)
        self.assertIn(target_res, error_msg)
        self.assertIn("got 2", error_msg)

    def test_handles_special_characters_in_resolution(self):
        """Test that function properly escapes special regex characters in resolution"""
        # Use resolution with actual regex special characters that are safe for filenames
        target_res = "f^09.g17+]test"

        expected_dir = self._create_test_case("test_case", target_res)

        result = _get_baseline_dir_with_files_from_run(
            self._which_script, self.baseline_dir, target_res
        )

        self.assertEqual(result, expected_dir)

    def test_resolution_must_match_exactly(self):
        """Test that resolution matching is exact (not substring)"""
        target_res = "f09"

        # Create case with resolution that contains target as substring
        self._create_test_case("test_case", "f09_g17")

        # Should not match because we're looking for exact "-res f09", not "-res f09_g17"
        with self.assertRaises(FileNotFoundError):
            _get_baseline_dir_with_files_from_run(self._which_script, self.baseline_dir, target_res)


if __name__ == "__main__":
    unit_testing.setup_for_tests()
    unittest.main()
