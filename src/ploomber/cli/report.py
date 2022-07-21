import click

from ploomber.cli.parsers import CustomParser
from ploomber.cli.io import cli_endpoint
from ploomber_core.telemetry import telemetry
from ploomber import __version__ as ver
from ploomber import POSTHOG_API_KEY as key

@cli_endpoint
@telemetry.log_call('report', 'ploomber', ver, key)
def main():
    parser = CustomParser(description='Make a pipeline report',
                          prog='ploomber report')
    with parser:
        parser.add_argument(
            '--output',
            '-o',
            help='Where to save the report, defaults to pipeline.html',
            default='pipeline.html')
        parser.add_argument(
            '--backend',
            '-b',
            help=('Decides on the backend to generate the plot: '
                  'd3 or pygraphviz, the one '
                  'available by default'),
            default=None)

    dag, args = parser.load_from_entry_point_arg()
    dag.to_markup(path=args.output, backend=args.backend)

    click.echo(f'Report saved at: {args.output}')
