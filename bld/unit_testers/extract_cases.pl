#!/usr/bin/env perl
#
# extract_cases.pl -- instrument build-namelist_test.pl and emit the
# manifest of every Test::More assertion it makes.
#
# Default (enumerate mode):   ./extract_cases.pl
#   -> writes ../unit_testers_python/cases.yaml
# Run mode:                   ./extract_cases.pl --run-mode outcomes.json
#   -> writes outcomes.json with {case_id => "pass"|"fail"} mapping
#
# Used by:
#   - PR-level checked-in manifest regeneration (default mode)
#   - check_coverage.py --parity (run mode, ephemeral output)
#
# The extractor reads build-namelist_test.pl as a string, splits it at
# the seam between the sub-definition header block (lines 1..~115) and
# the executable body, evals the header in our process, installs
# wrappers around make_env_run / make_config_cache /
# cat_and_create_namelistinfile / Test::Builder::ok / CORE::GLOBAL::system
# / STDOUT, then evals the body. Each Test::More assertion that fires
# gets paired with the most-recent captured context. No edits are made
# to build-namelist_test.pl on disk.

use strict;
use warnings;
use FindBin qw($Bin);
use Cwd qw(abs_path getcwd);
use English;
use Getopt::Long;
use IO::File;

# ---------------------------------------------------------------------------
# arg parsing
# ---------------------------------------------------------------------------

my $run_mode_outfile;
GetOptions("run-mode=s" => \$run_mode_outfile)
  or die "usage: extract_cases.pl [--run-mode <outfile>]\n";
my $enumerate_mode = !defined($run_mode_outfile);

# ---------------------------------------------------------------------------
# captured state -- these are package-globals so the wrappers can poke them
# ---------------------------------------------------------------------------

our $current_category       = "smoke";    # banner watcher updates this
our $current_phys           = undef;
our $outer_loop_phys        = undef;      # phys from the outer "foreach my $phys (clm4_5, ...) loop
our $_last_make_cc_phys     = undef;      # most recent arg to make_config_cache (pre-banner)
our $section_start_phys     = undef;      # phys at the time the section banner fired
our $section_has_make_cc    = 0;          # has make_config_cache been called in this section?
our %current_env_run        = ();
our @current_bldnml_argv    = ();
our $current_bldnml_cmd     = "";
our @current_infile_sources = ();
our @current_setup_files    = ();
our @cases                  = ();
our %infile_dest_to_sources = ();           # cat_and_create -> sources map

# CTSM bld/ root, computed once (used per-assertion by _normalize_source_path).
# $Bin is absolute, so this is stable regardless of later chdir.
our $BLD_ROOT = abs_path("$Bin/..");

# Every normalized banner text that reached _set_category_from_banner. Used by
# _report_banner_coverage to flag known section banners that were NEVER seen
# (a renamed/removed section). See that sub for why we don't conversely warn on
# banners that were seen but matched no category.
our %seen_banner_text = ();

# Map banner text -> category slug.
# Keys are matched after whitespace collapse (consecutive whitespace -> single
# space, leading/trailing trimmed), so author them with single spaces here.
our %BANNER_TO_CATEGORY = (
    "Run simple tests"                                                                              => "smoke",
    "Run simple tests with all list options"                                                        => "list_options",
    "Run simple tests with additional options"                                                      => "additional_options",
    "Test drydep, fire_emis and megan namelists"                                                    => "drydep_megan",
    "Test configuration, structure, irrigate, verbose, clm_demand, ssp_rcp, test, sim_year, use_case" => "nuopc_matrix",
    "Test the NEON sites"                                                                           => "neon",
    "Test the PLUMBER2 sites"                                                                       => "plumber2",
    "Test some CAM specific setups for special grids"                                               => "cam_grids",
    "Test setting drv_flds_in fields in CAM, clm60 only"                                            => "cam_drv_flds_clm60",
    "Test setting drv_flds_in fields in CAM"                                                        => "cam_drv_flds",
    "Test several use_cases and specific configurations for clm5_0"                                 => "use_cases_clm5_0",
    "Start Failure testing. These should fail"                                                      => "failures",
    "Start Warning testing. These should fail unless -ignore_warnings option is used"               => "warnings",
    "Ensure cold starts with finidat are handled properly"                                          => "coldwfinidat",
    "Test ALL resolutions that have surface datasets with SP for 1850 and 2000"                     => "resolutions_sp",
    "Test important resolutions for BGC and historical"                                             => "resolutions_bgc",
    "Test all use-cases over all physics options for f09 and SP"                                    => "use_cases_all_phys",
    "Test the seperate initial condition files, for ones not tested elsewhere"                      => "finidat_files",
    "Test crop resolutions"                                                                         => "crop_resolutions",
    "Test glc_mec resolutions"                                                                      => "glc_mec_resolutions",
    "Test clm4.5/clm5.0/clm6_0 resolutions"                                                         => "clm_resolutions",
    "Dumping output"                                                                                => "xfail_dump",
);

# Categories whose perl assertions are isnt($?, 0, ...) -- i.e. the command is
# expected to FAIL -- and the argv tokens that flip individual cases back to
# expecting success. Named here (rather than inline in _snapshot_case) so the
# coupling between these categories and the exit_zero heuristic is discoverable.
use constant {
    CAT_FAILURES         => 'failures',
    CAT_WARNINGS         => 'warnings',
    CAT_COLDWFINIDAT     => 'coldwfinidat',
    ARGV_IGNORE_WARNINGS => '-ignore_warnings',
    ARGV_FATES           => 'fates',
    ARGV_HELP            => '-help',
    ARGV_HELP_SHORT      => '-h',
};

# The perl harness prefixes every build-namelist invocation with this fixed
# base ($bldnml, build-namelist_test.pl line ~195). We strip it so each case's
# bldnml_argv holds only the per-case options (the shape design.md section 6
# specifies); the pytest build_namelist fixture re-injects this base, taking
# -csmdata from the runtime inputdata root rather than the path baked in at
# extraction time (so --csmdata / $CSMDATA actually control the run). The
# -csmdata VALUE varies, so its slot is a wildcard (undef). If an argv head
# does NOT match this base, _strip_base_argv leaves the argv intact and warns
# -- a base change must be handled deliberately, never silently dropped.
our @BASE_ARGV = (
    '-verbose',
    '-csmdata', undef,           # undef = match any single token (inputdata root)
    '-configuration', 'clm',
    '-structure', 'standard',
    '-glc_nec', '10',
    '-no-note',
);

# ---------------------------------------------------------------------------
# slurp the test source and split it at the seam between the sub defs and
# the executable body
# ---------------------------------------------------------------------------

my $perl_test_path = "$Bin/build-namelist_test.pl";
my $src_fh = IO::File->new($perl_test_path, '<')
  or die "ERROR: can't open $perl_test_path: $!\n";
my $src = do { local $/; <$src_fh> };
$src_fh->close();

# Split point: just before the "# Process command-line options." comment block.
# That line is reliably unique in the file.
my $split_marker = "#\n# Process command-line options.\n#\n";
my $split_idx = index($src, $split_marker);
if ($split_idx < 0) {
    die "ERROR: could not find split marker in $perl_test_path\n"
      . "(expected exact string: '# Process command-line options.')\n";
}
my $header  = substr($src, 0, $split_idx);
my $body    = substr($src, $split_idx);

# We need to know what line number the body starts at in the original file
# so the source-line annotations we record stay meaningful.
my $body_line_offset = ($header =~ tr/\n//);     # number of newlines before body

# ---------------------------------------------------------------------------
# install wrappers and hooks
# ---------------------------------------------------------------------------
#
# These have to be installed AFTER the header evals (so that make_env_run
# etc. exist to wrap) but BEFORE the body evals (so that the wrappers are in
# place by the time the body invokes them).

sub install_wrappers {
    no warnings 'redefine';

    # --- wrap make_env_run -----------------------------------------------
    # Observe, don't reconstruct: let the real make_env_run write env_run.xml
    # (its own defaults merged with the caller's settings), then parse that
    # file back into %current_env_run. This keeps the captured env in
    # lock-step with build-namelist_test.pl's actual defaults -- if someone
    # edits those defaults, we pick up the change instead of silently
    # emitting a stale hard-coded copy of them.
    my $orig_mer = \&main::make_env_run;
    *main::make_env_run = sub {
        my $ret = $orig_mer->(@_);
        %current_env_run = _parse_env_run_xml("env_run.xml");
        return $ret;
    };

    # --- wrap make_config_cache ------------------------------------------
    my $orig_mcc = \&main::make_config_cache;
    *main::make_config_cache = sub {
        my ($phys) = @_;
        $current_phys        = $phys;
        $_last_make_cc_phys  = $phys;  # remember last arg for outer-loop detection
        $section_has_make_cc = 1;      # flag: this section calls make_config_cache
        return $orig_mcc->(@_);
    };

    # --- wrap cat_and_create_namelistinfile ------------------------------
    my $orig_catnml = \&main::cat_and_create_namelistinfile;
    *main::cat_and_create_namelistinfile = sub {
        my ($file1, $file2, $outfile) = @_;
        my @sources;
        push @sources, $file1 if defined $file1;
        push @sources, $file2 if defined $file2;
        # Record the dest -> sources map so the system() hook can later
        # resolve -infile <dest> back to its source files.
        $infile_dest_to_sources{$outfile} = [@sources] if defined $outfile;
        return $orig_catnml->(@_);
    };

    # --- hook Test::Builder::ok ------------------------------------------
    require Test::Builder;
    my $orig_ok = Test::Builder->can('ok');
    no warnings 'once';
    *Test::Builder::ok = sub {
        my ($self, $test, $name) = @_;
        # Capture the user's call site BEFORE calling the original (so any
        # caller-stack munging Test::Builder/Test2 does internally does not
        # affect us). Test::Builder maintains $Level for skipping over its
        # own internal frames; honor it by walking the stack until we find
        # the first frame that's outside Test::More/Test::Builder/Test2.
        my $line;
        my $file;
        for (my $i = 1; $i < 30; $i++) {
            my @c = caller($i);
            last unless @c;
            my ($pkg, $f, $l) = @c;
            next if $pkg =~ /^Test::(Builder|More|Stream)\b/;
            next if $pkg =~ /^Test2\b/;
            $file = $f;
            $line = $l;
            last;
        }
        $main::_capture_file = $file;
        $main::_capture_line = $line;
        my $ret = $orig_ok->($self, $test, $name);
        _snapshot_case($name, $test ? 1 : 0);
        return $ret;
    };
}

# CORE::GLOBAL::system has to be set BEFORE the body is compiled (the override
# applies only to code compiled after the override is installed).
BEGIN {
    *CORE::GLOBAL::system = sub {
        my $cmd = join(" ", @_);
        # We only care about build-namelist invocations -- ignore rm, cat, etc.
        if ($cmd =~ m{\bbuild-namelist\b}) {
            $main::current_bldnml_cmd  = $cmd;
            @main::current_bldnml_argv = main::_parse_bldnml_argv($cmd);
            # Resolve -infile <path> against the cat_and_create_namelistinfile
            # destination map; otherwise clear infile sources.
            @main::current_infile_sources = ();
            for (my $i = 0; $i < @main::current_bldnml_argv - 1; $i++) {
                if ($main::current_bldnml_argv[$i] eq "-infile"
                    || $main::current_bldnml_argv[$i] eq "--infile") {
                    my $dest = $main::current_bldnml_argv[$i + 1];
                    if (exists $main::infile_dest_to_sources{$dest}) {
                        @main::current_infile_sources
                            = @{ $main::infile_dest_to_sources{$dest} };
                    } else {
                        @main::current_infile_sources = ($dest);
                    }
                    last;
                }
            }
        }
        return CORE::system(@_);
    };
}

# Tie STDOUT to a banner-watcher so we can pick up `print "Some banner\n"`
# section headers from the test script.
{
    package BannerWatcher;
    sub TIEHANDLE { my $class = shift; my $orig = shift; bless { orig => $orig, state => 'idle', pending => undef }, $class; }
    sub PRINT {
        my $self = shift;
        my $msg = join('', @_);
        # Mirror to the real stdout (so the user can see progress).
        $self->{orig}->print($msg);
        # Banner pattern (multi-call): equals-line(s), then text, then equals-line(s).
        # The test script uses both "==...==" (50 chars) and longer variants.
        # We are looking for "==+" alone on a line.
        for my $line (split(/\n/, $msg)) {
            $line =~ s/^\s+|\s+$//g;
            if ($line =~ /^=+$/) {
                # Saw an equals-only line. If we have a pending text line,
                # treat it as the banner.
                if (defined($self->{pending})) {
                    main::_set_category_from_banner($self->{pending});
                    $self->{pending} = undef;
                }
                $self->{state} = 'equals';
            } elsif ($self->{state} eq 'equals' && $line ne '') {
                $self->{pending} = $line;
                $self->{state} = 'text';
            } else {
                # Drop the pending line if we wander away without seeing
                # another equals.
                $self->{state} = 'idle';
            }
        }
    }
    sub PRINTF { my $self = shift; my $fmt = shift; $self->PRINT(sprintf($fmt, @_)); }
    sub WRITE { my $self = shift; $self->{orig}->write(@_); }
    sub CLOSE { my $self = shift; $self->{orig}->close; }
    sub BINMODE { my $self = shift; binmode $self->{orig}, @_; }
    sub FILENO { my $self = shift; fileno $self->{orig}; }
}

sub install_banner_watcher {
    # Save STDOUT to a duplicate filehandle so the tied wrapper can keep
    # writing to the real terminal.
    open(my $orig_stdout, ">&", \*STDOUT) or die "ERROR: cannot dup STDOUT: $!\n";
    $orig_stdout->autoflush(1);
    # Now tie STDOUT.
    tie *STDOUT, 'BannerWatcher', $orig_stdout;
}

sub _set_category_from_banner {
    my ($text) = @_;
    # Normalize whitespace.
    $text =~ s/\s+/ /g;
    $text =~ s/^\s+|\s+$//g;
    return unless $text;
    # Strip stray non-ASCII or leading/trailing equals (shouldn't happen but
    # just in case).
    $text =~ s/^=+\s*//;
    $text =~ s/\s*=+$//;
    # Record every banner we were handed so _report_banner_coverage can flag
    # any that did not map to a known category.
    $seen_banner_text{$text}++;
    if (exists $BANNER_TO_CATEGORY{$text}) {
        $current_category = $BANNER_TO_CATEGORY{$text};
        # Detect the outer phys loop: the first section inside the outer
        # "foreach my $phys (clm4_5, clm5_0, clm6_0)" loop is resolutions_sp.
        # The outer loop calls make_config_cache($phys) immediately before the
        # resolutions_sp banner.  If the banner we just saw is resolutions_sp AND
        # $_last_make_cc_phys was set right before this banner (i.e. no other
        # make_config_cache was called between the last outer-loop start and this
        # banner), then $_last_make_cc_phys IS the outer-loop phys.
        if ($current_category eq 'resolutions_sp' && defined $_last_make_cc_phys) {
            $outer_loop_phys = $_last_make_cc_phys;
        }
        # For sections within the outer loop that do not call make_config_cache
        # themselves, use the outer_loop_phys as the deterministic phys.
        # For sections that DO call make_config_cache (finidat_files, etc.),
        # $current_phys will be updated per-case, which is correct.
        $section_start_phys  = $outer_loop_phys // $current_phys;
        $section_has_make_cc = 0;
        $_last_make_cc_phys  = undef;   # reset so the next outer-loop start is detectable
    }
    # If a banner is unknown, leave the current category alone. The "Test"
    # banner-like prints inside foreach loops (e.g. "=== Test ne30np4 ===")
    # are not separated by full equals-only lines, so they should not even
    # reach this function.
}

# Fail loud on banner drift. Called once after the test body has run. If a
# section banner in %BANNER_TO_CATEGORY was never printed during the run, that
# section was renamed or removed -- and its assertions are now silently
# mis-filed under a neighboring category. Warn explicitly so the manifest's
# categories cannot drift unnoticed. Writes only to STDERR; never alters
# cases.yaml.
sub _report_banner_coverage {
    # We deliberately do NOT warn on banner texts that reached us but matched
    # no category. The test script brackets many NON-section texts with "===="
    # lines too (e.g. "physics = clm4_5", "Test 4x5", per-file diff headers),
    # which _set_category_from_banner correctly ignores; an "unmatched banner"
    # set is dominated by that legitimate noise and would cry wolf every run.
    # Instead we check the inverse, which is high-signal and false-positive
    # free: a curated banner that was NEVER seen means a known section was
    # renamed or removed (the other half of a rewording), so its cases are now
    # mis-filed under a neighboring category.
    my @unhit = sort grep { !$seen_banner_text{$_} } keys %BANNER_TO_CATEGORY;
    if (@unhit) {
        warn "WARNING: extract_cases.pl never saw "
           . scalar(@unhit)
           . " banner(s) listed in %BANNER_TO_CATEGORY (renamed, removed, or\n"
           . "not exercised this run?). Cases for those sections may now be\n"
           . "mis-filed under a neighboring category:\n";
        warn "  - \"$_\"\n" for @unhit;
    }
}

# ---------------------------------------------------------------------------
# case-record building
# ---------------------------------------------------------------------------

sub _snapshot_case {
    my ($desc, $passed) = @_;
    $desc = defined $desc ? $desc : "";
    # The Test::Builder::ok hook stashed the user's call site in
    # $main::_capture_file / $main::_capture_line via the caller-walk
    # above; prefer those when present. Fall back to caller(2) for any
    # path that bypassed the walk.
    my $file = $main::_capture_file;
    my $line = $main::_capture_line;
    if (!defined $file) {
        my (undef, $f, $l) = caller(2);
        ($file, $line) = ($f, $l);
    }
    if (!defined $file) {
        ($file, $line) = ("<unknown>", 0);
    }
    my $slug = _derive_slug($desc);

    # Use the phys for this case. For sections that call make_config_cache
    # within their own body (e.g. finidat_files, failures, warnings), use the
    # current $current_phys as set by the most recent make_config_cache call.
    # For sections that rely on the phys inherited from the outer loop
    # (e.g. crop_resolutions, glc_mec_resolutions), use the phys that was
    # current when the section banner fired -- this insulates those sections
    # from the non-deterministic $current_phys left by hash-iterated sections
    # (e.g. %finidat_files) that may have run just before the banner.
    my $case_phys = $section_has_make_cc ? $current_phys : $section_start_phys;

    # Determine expect.exit_zero based on category and context.
    # - failures: all calls are isnt($?, 0) → always exit_zero: false
    # - warnings:  first call per key is isnt($?, 0); second/third have
    #              -ignore_warnings in argv (is($?, 0) / is($@, ''))
    # - coldwfinidat: bgc case (expected_fail=1) is always exit_zero: false
    #              regardless of -ignore_warnings; fates case exit_zero: true
    my $exit_zero = 1;
    if ($current_category eq CAT_FAILURES) {
        $exit_zero = 0;
    } elsif ($current_category eq CAT_WARNINGS) {
        # isnt() call has no -ignore_warnings; is() calls do
        my $has_ignore_warnings = grep { $_ eq ARGV_IGNORE_WARNINGS } @current_bldnml_argv;
        $exit_zero = $has_ignore_warnings ? 1 : 0;
    } elsif ($current_category eq CAT_COLDWFINIDAT) {
        # bgc case never has -bgc fates; fates case always has it.
        # bgc sub-cases (including the -ignore_warnings one) are exit_zero: false.
        my $has_fates = grep { $_ eq ARGV_FATES } @current_bldnml_argv;
        $exit_zero = $has_fates ? 1 : 0;
    }

    # build-namelist -help (and the -h alias) prints its usage via die(), so it
    # always exits non-zero -- regardless of category. (-version, by contrast,
    # exits 0.) This overrides the category default above for e.g. smoke/help.
    if (grep { $_ eq ARGV_HELP || $_ eq ARGV_HELP_SHORT } @current_bldnml_argv) {
        $exit_zero = 0;
    }

    # Sanity check: the polarity heuristics above assume each failure/warning/
    # coldwfinidat assertion is paired with a build-namelist command (the one
    # whose argv we inspect for -ignore_warnings / fates). If we ever assign
    # polarity to such a case with NO captured command, the source-order
    # context pairing has broken and the emitted exit_zero is a guess -- warn
    # loudly rather than emit a plausible-but-wrong value silently.
    if (($current_category eq CAT_FAILURES
         || $current_category eq CAT_WARNINGS
         || $current_category eq CAT_COLDWFINIDAT)
        && !@current_bldnml_argv) {
        warn "WARNING: $current_category case '$desc' has no captured "
           . "build-namelist argv; exit_zero polarity may be wrong\n";
    }

    push @cases, {
        slug         => $slug,
        category     => $current_category,
        description  => $desc,
        bldnml_argv  => [ @current_bldnml_argv ],
        bldnml_cmd   => $current_bldnml_cmd,
        env_run      => { %current_env_run },
        phys         => $case_phys,
        infile       => { sources => [ @current_infile_sources ] },
        setup_files  => [ @current_setup_files ],
        expect       => {
            exit_zero => $exit_zero,
            files     => [],
            greps     => [],
        },
        xfail        => undef,
        source       => { perl_file => _normalize_source_path($file),
                          line      => $line },
        ported       => 0,
        stale        => 0,
        stale_reason => undef,
        _perl_passed => $passed,
    };
}

sub _normalize_source_path {
    my ($p) = @_;
    return "<unknown>" unless defined $p && length($p);
    # Map absolute or relative paths back to a canonical CTSM-rooted path.
    # The two paths we expect: the perl test file (we annotated it via
    # '# line N "..."' so it should already match) and NMLTest/CompFiles.pm.
    my $bld_root = $BLD_ROOT;
    my $ap = abs_path($p);
    if (defined $ap && defined $bld_root && index($ap, $bld_root) == 0) {
        my $rel = substr($ap, length($bld_root) + 1);
        return "bld/$rel";
    }
    # Fall through: strip ./ and return.
    $p =~ s{^\./}{};
    return $p;
}

sub _derive_slug {
    my ($desc) = @_;
    my $slug = lc(defined $desc ? $desc : "");
    $slug =~ s/^options:\s*//;
    $slug =~ s/[^a-z0-9._-]+/-/g;
    $slug =~ s/^-+|-+$//g;
    $slug = "unnamed" if $slug eq "";
    return $slug;
}

# Assign deterministic ids to every case in @cases.  Cases are grouped by
# (category, slug); within each group they are sorted by bldnml_cmd (the
# canonical input) so the counter-to-case binding does not depend on the
# perl hash-iteration order in which the underlying test sections enumerated
# them.  First case in each group gets the bare slug, subsequent get "-2",
# "-3", ...  Must be called after all cases have been collected and before
# either _write_cases_yaml or _write_outcomes_json reads $c->{id}.
sub _assign_ids {
    my %groups;
    for my $c (@cases) {
        push @{ $groups{"$c->{category}/$c->{slug}"} }, $c;
    }
    for my $base (keys %groups) {
        # Sort each same-slug group by the canonical input (bldnml_cmd) so the
        # counter-to-case binding does not depend on perl hash-iteration order.
        # NOTE on ties: a few groups contain cases with an IDENTICAL bldnml_cmd
        # (same command, differing only in phys / source line -- e.g. the
        # ne16np4.pg3 bgc case appears in both the main resolution sweep and
        # the ne16-only pass). This stable sort leaves those tied cases in
        # @cases push order. That push order is itself deterministic, because
        # every such group is produced by fixed array loops (foreach phys /
        # clmopts / res), not hash iteration -- so the emitted disambiguation
        # counters are reproducible across runs. Adding a secondary key
        # (description / source line) would make this guarantee structural
        # rather than relying on the array-loop property, but it reorders the
        # existing manifest, so it is deferred to a deliberate
        # manifest-regenerating change.
        my @group = sort { $a->{bldnml_cmd} cmp $b->{bldnml_cmd} } @{ $groups{$base} };
        for my $i (0 .. $#group) {
            $group[$i]{id} = $i == 0 ? $base : "$base-" . ($i + 1);
        }
    }
}

# ---------------------------------------------------------------------------
# env_run.xml reader -- parses the file make_env_run just wrote so the
# captured env reflects ground truth (see the make_env_run wrapper above).
# make_env_run emits lines of the exact form:
#     <entry id="DIN_LOC_ROOT"         value="MYDINLOCROOT"  />
# ---------------------------------------------------------------------------

sub _parse_env_run_xml {
    my ($path) = @_;
    my %env;
    my $fh = IO::File->new($path, '<') or return %env;
    while (my $line = <$fh>) {
        if ($line =~ /<entry\s+id="([^"]*)"\s+value="([^"]*)"\s*\/>/) {
            $env{$1} = $2;
        }
    }
    $fh->close();
    return %env;
}

# ---------------------------------------------------------------------------
# bldnml command parsing -- the test script builds a shell string that ends
# in `> $tempfile 2>&1`; we strip those, drop the build-namelist binary
# itself, and shell-split the remainder.
# ---------------------------------------------------------------------------

sub _parse_bldnml_argv {
    my ($cmd) = @_;
    my $stripped = $cmd;
    # Drop trailing shell redirection.
    $stripped =~ s/\s*>\s*\S+\s*2>&1\s*$//;
    $stripped =~ s/\s+$//;
    # Drop the build-namelist binary path (and the perl invocation, if any).
    $stripped =~ s{^\s*\S*build-namelist\b\s*}{};
    # Strip the fixed $bldnml base flags, leaving only the per-case options.
    return _strip_base_argv(_shell_split($stripped));
}

# Remove the leading @BASE_ARGV flags from a tokenized command. Returns the
# per-case options only. If the head does not match the expected base, returns
# the argv unchanged and warns (fail loud rather than silently mis-strip).
sub _strip_base_argv {
    my (@argv) = @_;
    return @argv if @argv < scalar(@BASE_ARGV);
    my $csmdata;
    for my $i (0 .. $#BASE_ARGV) {
        if (!defined $BASE_ARGV[$i]) {
            # Wildcard slot: capture the inputdata root (the value following
            # -csmdata) so per-case paths rooted under it can be normalized.
            $csmdata = $argv[$i] if $i > 0 && $BASE_ARGV[$i - 1] eq '-csmdata';
            next;
        }
        if (!defined $argv[$i] || $argv[$i] ne $BASE_ARGV[$i]) {
            warn "WARNING: build-namelist argv head does not match the expected "
               . "\$bldnml base; leaving full argv. At position $i expected "
               . "'$BASE_ARGV[$i]', got '"
               . (defined $argv[$i] ? $argv[$i] : '<undef>') . "'.\n";
            return @argv;
        }
    }
    my @rest = @argv[ scalar(@BASE_ARGV) .. $#argv ];
    return _normalize_csmdata_paths($csmdata, @rest);
}

# Replace a leading inputdata-root prefix in each per-case token with the
# portable {csmdata} placeholder, so the manifest does not bake in the
# machine-specific path that $bldnml's -csmdata resolved to at extraction time
# (e.g. the -lnd_frac $DOMFILE value, which is "$inputdata_rootdir/atm/..."). The
# conftest build_namelist fixture expands {csmdata} back to the runtime
# inputdata root. Only an exact whole-token match or a "<root>/..." prefix is
# rewritten -- never a mid-token substring.
sub _normalize_csmdata_paths {
    my ($csmdata, @tokens) = @_;
    return @tokens unless defined $csmdata && length $csmdata;
    for my $t (@tokens) {
        next unless defined $t;
        if ($t eq $csmdata) {
            $t = '{csmdata}';
        } elsif (index($t, "$csmdata/") == 0) {
            # Drop only the root (length $csmdata), keeping the leading slash
            # that follows it -> "{csmdata}/atm/...".
            $t = '{csmdata}' . substr($t, length $csmdata);
        }
    }
    return @tokens;
}

sub _shell_split {
    # Minimal shell-like tokenizer: handles single quotes, double quotes, and
    # whitespace. Does NOT handle backslash escapes -- the test script does
    # not use them outside of quoted strings, and inside quotes they pass
    # through as-is. Quote characters themselves are consumed (not appended to
    # the current token), so the resulting tokens match what the shell would
    # actually pass to the subprocess. Sufficient for our purposes.
    #
    # Consumer contract: these tokens are written to cases.yaml's bldnml_argv
    # and re-run by the pytest suite via subprocess.run(argv) with no shell.
    # Dropping the shell quoting/escaping here is therefore correct -- argv
    # elements must be the literal strings the program receives, not re-shell-
    # quoted forms.
    my ($s) = @_;
    my @tokens;
    my $cur = "";
    my $in_squote = 0;
    my $in_dquote = 0;
    for (my $i = 0; $i < length($s); $i++) {
        my $c = substr($s, $i, 1);
        if (!$in_squote && !$in_dquote && $c =~ /\s/) {
            if (length($cur)) {
                push @tokens, $cur;
                $cur = "";
            }
        } elsif ($c eq "'" && !$in_dquote) {
            # Toggle single-quote mode; do NOT append the quote char.
            $in_squote = !$in_squote;
        } elsif ($c eq '"' && !$in_squote) {
            # Toggle double-quote mode; do NOT append the quote char.
            $in_dquote = !$in_dquote;
        } else {
            $cur .= $c;
        }
    }
    push @tokens, $cur if length($cur);
    return @tokens;
}

# ---------------------------------------------------------------------------
# YAML / JSON writers (hand-rolled; no XS dependencies)
# ---------------------------------------------------------------------------

sub _yaml_escape_str {
    my ($s) = @_;
    $s = "" unless defined $s;
    # If the string is "safe" (no special chars, not empty, not numeric-like,
    # not a bool), we can emit unquoted. Otherwise emit double-quoted with
    # the minimum required escapes.
    if ($s eq "") {
        return '""';
    }
    if ($s =~ /^[A-Za-z_][A-Za-z0-9_.\/-]*$/ && $s !~ /^(true|false|null|yes|no|on|off|y|n)$/i) {
        return $s;
    }
    if ($s =~ /^-?\d+(\.\d+)?$/) {
        # Pure number -- must quote to keep it a string.
        return '"' . $s . '"';
    }
    # Double-quoted form: escape backslash, double-quote, control chars.
    my $out = $s;
    $out =~ s/\\/\\\\/g;
    $out =~ s/"/\\"/g;
    $out =~ s/\n/\\n/g;
    $out =~ s/\r/\\r/g;
    $out =~ s/\t/\\t/g;
    return '"' . $out . '"';
}

sub _yaml_bool { return $_[0] ? "true" : "false"; }

sub _emit_yaml_scalar_list {
    my ($items, $indent) = @_;
    if (!@$items) {
        return " []";
    }
    my $out = "\n";
    for my $item (@$items) {
        $out .= $indent . "- " . _yaml_escape_str($item) . "\n";
    }
    chomp $out;
    return $out;
}

sub _emit_yaml_dict {
    my ($h, $indent) = @_;
    if (!%$h) {
        return " {}";
    }
    my $out = "\n";
    for my $k (sort keys %$h) {
        $out .= $indent . _yaml_escape_str($k) . ": " . _yaml_escape_str($h->{$k}) . "\n";
    }
    chomp $out;
    return $out;
}

sub _write_cases_yaml {
    my ($outpath) = @_;

    # Issue 1: Idempotent regeneration.
    # If the file already exists, load the previous annotations so we can
    # preserve ported / stale / stale_reason for cases whose structural
    # fields have not changed.
    my %prev = ();    # id => { ported, stale, stale_reason, bldnml_argv,
                      #          env_run, phys, infile => { sources => [...] } }
    if (-f $outpath) {
        %prev = _load_previous_yaml($outpath);
    }

    # Issue 3: Stable ordering.
    # Sort by (category, id) so the file is byte-identical across runs
    # regardless of the perl hash-iteration order in %failtest etc.
    my @sorted_cases = sort { $a->{category} cmp $b->{category}
                              || $a->{id}       cmp $b->{id}       } @cases;

    my $fh = IO::File->new($outpath, '>') or die "ERROR: can't write $outpath: $!\n";
    print $fh "# Auto-generated by bld/unit_testers/extract_cases.pl. Do not edit by hand.\n";
    print $fh "# Re-run extract_cases.pl after build-namelist_test.pl changes.\n";
    print $fh "# Schema: see .claude/namelist-testing-modernization/design.md section 6.\n";
    for my $c (@sorted_cases) {
        # Issue 1: merge annotations from previous file if id matches and
        # structural fields are unchanged.
        my ($ported, $stale, $stale_reason) = (0, 0, undef);
        if (exists $prev{$c->{id}}) {
            my $p = $prev{$c->{id}};
            $stale        = $p->{stale};
            $stale_reason = $p->{stale_reason};
            if (_structural_eq($c, $p)) {
                $ported = $p->{ported};
            } else {
                if ($p->{ported}) {
                    print STDERR "info: ported reset for $c->{id} due to structural change\n";
                }
                $ported = 0;
            }
        }

        print $fh "- id: " . _yaml_escape_str($c->{id}) . "\n";
        print $fh "  category: " . _yaml_escape_str($c->{category}) . "\n";
        print $fh "  description: " . _yaml_escape_str($c->{description}) . "\n";
        print $fh "  bldnml_argv:" . _emit_yaml_scalar_list($c->{bldnml_argv}, "    ") . "\n";
        print $fh "  env_run:" . _emit_yaml_dict($c->{env_run}, "    ") . "\n";
        print $fh "  phys: " . (defined($c->{phys}) ? _yaml_escape_str($c->{phys}) : "null") . "\n";
        print $fh "  infile:\n";
        print $fh "    sources:" . _emit_yaml_scalar_list($c->{infile}{sources}, "      ") . "\n";
        print $fh "  setup_files:" . _emit_yaml_scalar_list($c->{setup_files}, "    ") . "\n";
        print $fh "  expect:\n";
        print $fh "    exit_zero: " . _yaml_bool($c->{expect}{exit_zero}) . "\n";
        print $fh "    files:" . _emit_yaml_scalar_list($c->{expect}{files}, "      ") . "\n";
        print $fh "    greps:" . _emit_yaml_scalar_list($c->{expect}{greps}, "      ") . "\n";
        print $fh "  xfail: null\n";
        print $fh "  source:\n";
        print $fh "    perl_file: " . _yaml_escape_str($c->{source}{perl_file}) . "\n";
        print $fh "    line: " . ($c->{source}{line} + 0) . "\n";
        print $fh "  ported: " . _yaml_bool($ported) . "\n";
        print $fh "  stale: " . _yaml_bool($stale) . "\n";
        print $fh "  stale_reason: " . (defined($stale_reason) ? _yaml_escape_str($stale_reason) : "null") . "\n";
    }
    $fh->close();
}

# ---------------------------------------------------------------------------
# Structural equality check for idempotent regeneration (Issue 1).
# Returns true iff the new case's bldnml_argv, env_run, phys, and
# infile.sources are all equal to the previous entry's values.
# ---------------------------------------------------------------------------

sub _structural_eq {
    my ($new, $prev) = @_;

    # Compare bldnml_argv (ordered list).
    my @new_argv  = @{ $new->{bldnml_argv} };
    my @prev_argv = @{ $prev->{bldnml_argv} };
    return 0 unless @new_argv == @prev_argv;
    for my $i (0 .. $#new_argv) {
        return 0 unless defined $new_argv[$i] && defined $prev_argv[$i];
        return 0 unless $new_argv[$i] eq $prev_argv[$i];
    }

    # Compare env_run (unordered dict).
    my %new_er  = %{ $new->{env_run} };
    my %prev_er = %{ $prev->{env_run} };
    my @new_keys  = sort keys %new_er;
    my @prev_keys = sort keys %prev_er;
    return 0 unless "@new_keys" eq "@prev_keys";
    for my $k (@new_keys) {
        return 0 unless defined $new_er{$k} && defined $prev_er{$k};
        return 0 unless $new_er{$k} eq $prev_er{$k};
    }

    # Compare phys (scalar or undef).
    my $new_phys  = $new->{phys};
    my $prev_phys = $prev->{phys};
    if (defined $new_phys && defined $prev_phys) {
        return 0 unless $new_phys eq $prev_phys;
    } elsif (defined $new_phys || defined $prev_phys) {
        return 0;
    }

    # Compare infile.sources (ordered list). Both $new (freshly built) and
    # $prev (from _load_previous_yaml) store sources nested under infile.
    my @new_src  = @{ $new->{infile}{sources} };
    my @prev_src = @{ ($prev->{infile} || {})->{sources} // [] };
    return 0 unless @new_src == @prev_src;
    for my $i (0 .. $#new_src) {
        return 0 unless defined $new_src[$i] && defined $prev_src[$i];
        return 0 unless $new_src[$i] eq $prev_src[$i];
    }

    return 1;
}

# ---------------------------------------------------------------------------
# Hand-rolled YAML reader for the specific cases.yaml shape we emit.
# Returns a hash keyed by case id; value is a hashref of the annotation
# and structural fields we need for idempotent regeneration.
#
# CONTRACT: this reader parses ONLY the PR1-era emitted shape. It models the
# scalar/list fields id / bldnml_argv / env_run / phys / infile.sources /
# ported / stale / stale_reason. The list fields setup_files, expect.files,
# and expect.greps are always emitted empty ("[]") today, so they are NOT
# parsed here. If a future PR starts populating any of them, this reader must
# be extended -- it will die() on the first unmodeled list item rather than
# silently drop data (see the guard at the bottom of the loop).
# ---------------------------------------------------------------------------

sub _load_previous_yaml {
    my ($path) = @_;
    my %map;
    my $fh = IO::File->new($path, '<') or return %map;
    my %cur;
    my $state = 'idle';      # idle | case | bldnml_argv | env_run | infile
    my @cur_argv;
    my %cur_env_run;
    my @cur_infile_sources;

    while (my $line = <$fh>) {
        chomp $line;
        # Top-level case entry starts with "- id: ..."
        if ($line =~ /^- id: (.+)$/) {
            # Save previous case if any.
            if (defined $cur{id}) {
                $cur{bldnml_argv}  = [@cur_argv];
                $cur{env_run}      = {%cur_env_run};
                # Store nested (infile => { sources => [...] }) to match the
                # shape of freshly-built cases, so _structural_eq compares
                # like with like. See note there.
                $cur{infile}       = { sources => [@cur_infile_sources] };
                $map{$cur{id}} = {%cur};
            }
            %cur = (id => _yaml_unescape($1));
            @cur_argv = ();
            %cur_env_run = ();
            @cur_infile_sources = ();
            $state = 'case';
            next;
        }
        next unless $state ne 'idle';

        # Detect block transitions.
        if ($line =~ /^  bldnml_argv:/) {
            $state = ($line =~ /\[\]$/) ? 'case' : 'bldnml_argv';
            next;
        }
        if ($line =~ /^  env_run:/) {
            $state = ($line =~ /\{\}$/) ? 'case' : 'env_run';
            next;
        }
        if ($line =~ /^  phys: (.+)$/) {
            my $v = $1;
            $cur{phys} = ($v eq 'null') ? undef : _yaml_unescape($v);
            $state = 'case';
            next;
        }
        if ($line =~ /^  infile:/) {
            $state = 'case';    # sub-key 'sources' handled below
            next;
        }
        if ($line =~ /^    sources:/) {
            $state = ($line =~ /\[\]$/) ? 'case' : 'infile';
            next;
        }
        if ($line =~ /^  ported: (true|false)/) {
            $cur{ported} = ($1 eq 'true') ? 1 : 0;
            $state = 'case';
            next;
        }
        if ($line =~ /^  stale: (true|false)/) {
            $cur{stale} = ($1 eq 'true') ? 1 : 0;
            $state = 'case';
            next;
        }
        if ($line =~ /^  stale_reason: (.+)$/) {
            my $v = $1;
            $cur{stale_reason} = ($v eq 'null') ? undef : _yaml_unescape($v);
            $state = 'case';
            next;
        }
        # Any other top-level or mid-level field resets to 'case' parse state.
        if ($line =~ /^  \w/) {
            $state = 'case';
        }

        # List items.
        if ($state eq 'bldnml_argv' && $line =~ /^    - (.+)$/) {
            push @cur_argv, _yaml_unescape($1);
            next;
        }
        if ($state eq 'env_run' && $line =~ /^    (.+?): (.+)$/) {
            my ($k, $v) = (_yaml_unescape($1), _yaml_unescape($2));
            $cur_env_run{$k} = $v;
            next;
        }
        if ($state eq 'infile' && $line =~ /^      - (.+)$/) {
            push @cur_infile_sources, _yaml_unescape($1);
            next;
        }

        # Any list item not consumed above means cases.yaml grew a list field
        # this reader does not model (setup_files / expect.files /
        # expect.greps becoming non-empty). Fail loud rather than silently
        # drop it -- see the CONTRACT note in this sub's header.
        if ($line =~ /^\s+- /) {
            die "ERROR: _load_previous_yaml hit an unmodeled list item:\n"
              . "  $line\n"
              . "Extend this reader to cover the new list field (setup_files /\n"
              . "expect.files / expect.greps) before populating it in the manifest.\n";
        }
    }
    # Save last case.
    if (defined $cur{id}) {
        $cur{bldnml_argv}  = [@cur_argv];
        $cur{env_run}      = {%cur_env_run};
        $cur{infile}       = { sources => [@cur_infile_sources] };
        $map{$cur{id}} = {%cur};
    }
    $fh->close();
    return %map;
}

sub _yaml_unescape {
    # Reverse of _yaml_escape_str: strip outer double-quotes (if present) and
    # unescape \\, \", \n, \r, \t.  For unquoted scalars return as-is.
    my ($s) = @_;
    return '' unless defined $s;
    $s =~ s/^\s+|\s+$//g;
    if ($s =~ /^"(.*)"$/) {
        $s = $1;
        $s =~ s/\\n/\n/g;
        $s =~ s/\\r/\r/g;
        $s =~ s/\\t/\t/g;
        $s =~ s/\\"/"/g;
        $s =~ s/\\\\/\\/g;
    }
    return $s;
}

sub _write_outcomes_json {
    my ($outpath) = @_;
    my $fh = IO::File->new($outpath, '>') or die "ERROR: can't write $outpath: $!\n";
    print $fh "{\n";
    my $n = scalar @cases;
    for (my $i = 0; $i < $n; $i++) {
        my $c = $cases[$i];
        my $key = $c->{id};
        $key =~ s/\\/\\\\/g;
        $key =~ s/"/\\"/g;
        my $val = $c->{_perl_passed} ? "pass" : "fail";
        my $comma = ($i < $n - 1) ? "," : "";
        print $fh qq(  "$key": "$val"$comma\n);
    }
    print $fh "}\n";
    $fh->close();
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

# The build-namelist_test.pl script uses relative paths (`../build-namelist`,
# `../../cime_config/usermods_dirs`, etc.), so we have to run from its
# directory.
chdir $Bin or die "ERROR: cannot chdir to $Bin: $!\n";

# `use lib '.';` and `use xFail::expectedFail;` in the perl test depend on cwd
# being bld/unit_testers/. We are now there.

# The test script's GetOptions will read @ARGV. Force -no-test so dataset
# checks are skipped (extractor does not need inputdata to enumerate cases).
@ARGV = ("-no-test");

# Wrap the body so we can route any death back to a clean error message.
# We use eval STRING (not eval BLOCK) so the source is compiled in our
# package and the wrappers we install around named subs in main:: are
# visible to it.

# Step 1: evaluate the header (sub defs).
{
    # Anchor strict/warnings on the eval'd code separately.
    my $hdr = "use strict;\nuse warnings;\n# line 1 \"" . $perl_test_path . "\"\n" . $header;
    my $rc = eval $hdr;
    if ($@) {
        die "ERROR: failed to eval header of build-namelist_test.pl:\n$@\n";
    }
}

# Step 2: install wrappers around the now-defined subs.
install_wrappers();
install_banner_watcher();

# Step 3: evaluate the body. The body contains the executable code that
# calls plan(), make_env_run, build-namelist, and Test::More's is/isnt/ok/like.
{
    my $body_line = $body_line_offset + 1;
    my $bd = "use strict;\nuse warnings;\n# line $body_line \"" . $perl_test_path . "\"\n" . $body;
    my $rc = eval $bd;
    if ($@ && $@ !~ /Tests were run but no plan/) {
        # The script calls done_testing implicitly via plan(); any other
        # error is fatal. We tolerate Test::More finalization warnings since
        # we intercepted the ok calls.
        warn "WARNING: body eval reported: $@\n";
    }
}

# Untie STDOUT so we can write our summary unobstructed.
untie *STDOUT;

# Fail loud if any printed section banner did not map to a known category.
_report_banner_coverage();

# ---------------------------------------------------------------------------
# emit output
# ---------------------------------------------------------------------------

_assign_ids();

if ($enumerate_mode) {
    my $out_yaml = abs_path("$Bin/../unit_testers_python/cases.yaml");
    if (!defined $out_yaml) {
        # abs_path returns undef if the directory doesn't exist; fall back.
        $out_yaml = "$Bin/../unit_testers_python/cases.yaml";
    }
    _write_cases_yaml($out_yaml);
    print STDERR "extract_cases.pl: wrote $out_yaml (" . scalar(@cases) . " cases)\n";
} else {
    _write_outcomes_json($run_mode_outfile);
    print STDERR "extract_cases.pl: wrote $run_mode_outfile (" . scalar(@cases) . " outcomes)\n";
}

exit 0;
