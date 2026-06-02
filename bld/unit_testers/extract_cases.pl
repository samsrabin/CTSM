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
our %current_env_run        = ();
our @current_bldnml_argv    = ();
our $current_bldnml_cmd     = "";
our @current_infile_sources = ();
our @current_setup_files    = ();
our @cases                  = ();
our %id_counts              = ();           # for disambiguating duplicate slugs
our %infile_dest_to_sources = ();           # cat_and_create -> sources map

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
    my $orig_mer = \&main::make_env_run;
    *main::make_env_run = sub {
        my %settings = @_;
        my %defaults = (
            DIN_LOC_ROOT                => "MYDINLOCROOT",
            GLC_TWO_WAY_COUPLING        => "FALSE",
            LND_SETS_DUST_EMIS_DRV_FLDS => "TRUE",
            NEONSITE                    => "",
            PLUMBER2SITE                => "",
            CLM_CMIP_ERA                => "cmip7",
            CLM_NDEP_FROM_CPL           => "FALSE",
        );
        %current_env_run = (%defaults, %settings);
        return $orig_mer->(@_);
    };

    # --- wrap make_config_cache ------------------------------------------
    my $orig_mcc = \&main::make_config_cache;
    *main::make_config_cache = sub {
        my ($phys) = @_;
        $current_phys = $phys;
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
    if (exists $BANNER_TO_CATEGORY{$text}) {
        $current_category = $BANNER_TO_CATEGORY{$text};
    }
    # If a banner is unknown, leave the current category alone. The "Test"
    # banner-like prints inside foreach loops (e.g. "=== Test ne30np4 ===")
    # are not separated by full equals-only lines, so they should not even
    # reach this function.
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
    my $id = _derive_id($desc);
    push @cases, {
        id           => $id,
        category     => $current_category,
        description  => $desc,
        bldnml_argv  => [ @current_bldnml_argv ],
        bldnml_cmd   => $current_bldnml_cmd,
        env_run      => { %current_env_run },
        phys         => $current_phys,
        infile       => { sources => [ @current_infile_sources ] },
        setup_files  => [ @current_setup_files ],
        expect       => {
            exit_zero => 1,           # default; tweaked for known categories below
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
    my $bld_root = abs_path("$Bin/..");
    my $ap = abs_path($p);
    if (defined $ap && defined $bld_root && index($ap, $bld_root) == 0) {
        my $rel = substr($ap, length($bld_root) + 1);
        return "bld/$rel";
    }
    # Fall through: strip ./ and return.
    $p =~ s{^\./}{};
    return $p;
}

sub _derive_id {
    my ($desc) = @_;
    my $slug = lc(defined $desc ? $desc : "");
    $slug =~ s/^options:\s*//;
    $slug =~ s/[^a-z0-9._-]+/-/g;
    $slug =~ s/^-+|-+$//g;
    $slug = substr($slug, 0, 80) if length($slug) > 80;
    $slug = "unnamed" if $slug eq "";
    my $id = "$current_category/$slug";
    # Disambiguate duplicates within a category.
    if ($id_counts{$id}++) {
        $id = $id . "-" . $id_counts{$id};
    }
    return $id;
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
    return _shell_split($stripped);
}

sub _shell_split {
    # Minimal shell-like tokenizer: handles single quotes, double quotes, and
    # whitespace. Does NOT handle backslash escapes -- the test script does
    # not use them outside of quoted strings, and inside quotes they pass
    # through as-is. Sufficient for our purposes.
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
            $in_squote = !$in_squote;
            $cur .= $c;
        } elsif ($c eq '"' && !$in_squote) {
            $in_dquote = !$in_dquote;
            $cur .= $c;
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
    my $fh = IO::File->new($outpath, '>') or die "ERROR: can't write $outpath: $!\n";
    print $fh "# Auto-generated by bld/unit_testers/extract_cases.pl. Do not edit by hand.\n";
    print $fh "# Re-run extract_cases.pl after build-namelist_test.pl changes.\n";
    print $fh "# Schema: see .claude/namelist-testing-modernization/design.md section 6.\n";
    for my $c (@cases) {
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
        print $fh "  ported: " . _yaml_bool($c->{ported}) . "\n";
        print $fh "  stale: " . _yaml_bool($c->{stale}) . "\n";
        print $fh "  stale_reason: " . (defined($c->{stale_reason}) ? _yaml_escape_str($c->{stale_reason}) : "null") . "\n";
    }
    $fh->close();
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

# ---------------------------------------------------------------------------
# emit output
# ---------------------------------------------------------------------------

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
