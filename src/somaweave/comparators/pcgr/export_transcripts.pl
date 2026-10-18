#!/usr/bin/env perl
# Run with the PCGR 2.2.5 container's Perl/Storable. Inputs are read-only.
# Usage: perl export_transcripts.pl VEP_CACHE selected_mane_transcripts.json
# Selected transcript rows come from the matching bundle's gene_transcript_xref.
# No database adaptor or network call is made; models are printed as JSON.
use strict;
use warnings;
use Storable qw(fd_retrieve);
use JSON::PP;
my ($cache, $selected_file) = @ARGV;
die "usage: export_transcripts.pl VEP_CACHE selected.json\n" unless $selected_file;
open my $in, '<', $selected_file or die $!;
local $/;
my $selected = decode_json(<$in>);
my %models;
for my $gene (sort keys %$selected) {
    my $s = $selected->{$gene};
    my $chr = $s->{chrom};
    my $acc = $s->{ensembl_transcript_id};
    my $start = int(($s->{transcript_start} - 1) / 1000000) * 1000000 + 1;
    my $end = int(($s->{transcript_end} - 1) / 1000000) * 1000000 + 1;
    my $found;
    for (my $block = $start; $block <= $end; $block += 1000000) {
        my $file = "$cache/homo_sapiens/113_GRCh38/$chr/$block-" . ($block + 999999) . '.gz';
        open my $fh, '-|', 'gzip', '-dc', $file or die $!;
        my $data = fd_retrieve($fh);
        close $fh or die "cache decompression failed";
        for my $t (@{$data->{$chr}}) {
            next unless ($t->{stable_id} // '') eq $acc;
            my $v = $t->{_variation_effect_feature_cache};
            $found = {gene => $gene, chrom => $chr, transcript => $s->{ensembl_transcript_id_full},
                      strand => $t->{strand}, cds => $v->{translateable_seq}, peptide => $v->{peptide},
                      coding_start => $v->{mapper}{cdna_coding_start},
                      exons => [map {{start => $_->{start}, end => $_->{end}}} @{$t->{_trans_exon_array}}]};
            last;
        }
        last if $found;
    }
    die "No transcript cache model for $gene" unless $found;
    $models{$gene} = $found;
}
print JSON::PP->new->canonical->pretty->encode(\%models);
