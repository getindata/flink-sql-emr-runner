#!/usr/bin/env python3
import argparse
import logging
import os
import tempfile
from typing import List

import yaml

from deploy_job import EmrJobRunner, FlinkCliRunner, JinjaTemplateResolver

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')


def parse_args():
    # Parse cmd line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        required=True,
        help="Path where query definition files are stored.")
    parser.add_argument(
        "--template-file",
        required=True,
        help="Path to the job configuration defaults.")
    parser.add_argument(
        "--pyflink-runner-dir",
        required=True,
        help="Path to the directory containing PyFlink job runners.")
    parser.add_argument(
        "--external-job-config-bucket",
        required=True,
        help="S3 bucket where job configuration is stored.")
    parser.add_argument(
        "--external-job-config-prefix",
        required=True,
        help="S3 prefix where job configuration is stored.")
    parser.add_argument(
        "--table-definition-path",
        nargs='+',
        required=True,
        help="Paths to files containing common Flink table definitions.")

    return parser.parse_known_args()


def list_query_files(base_path: str) -> List[str]:
    result = []
    for (root, dirs, files) in os.walk(base_path):
        for f in files:
            if f.endswith(".yaml"):
                result.append(os.path.abspath(os.path.join(root, f)))
    return result


def read_config(query_file, template_file):
    # FIXME: refactor variables resolutions and yaml merge
    with open(query_file) as qf:
        query_specification = yaml.load(qf, yaml.FullLoader)
        if "sql" in query_specification:
            query_specification["sql"] = query_specification["sql"].replace("\n", " ")
        with open(template_file) as tf:
            raw_defaults = tf.read().format(job_name=query_specification["name"])
            default_config = yaml.safe_load(raw_defaults)
            final_flink_props = {**default_config["flinkProperties"], **query_specification["flinkProperties"]}
            final_config = {**default_config, **query_specification}
            final_config["flinkProperties"] = final_flink_props
            final_config["flinkProperties"]["pipeline.name"] = query_specification["name"]
            logging.info(f"Final configuration:\n{final_config}")
            return final_config


if __name__ == "__main__":
    args, _ = parse_args()
    query_files = list_query_files(args.path)

    for query_file in query_files:
        final_config = read_config(query_file, args.template_file)
        query_name = final_config["name"]
        with tempfile.NamedTemporaryFile(mode="w+t", prefix=query_name, suffix=".yaml") as tmp:
            yaml.dump(final_config, tmp)
            flink_cli_runner = FlinkCliRunner()
            jinja_template_resolver = JinjaTemplateResolver()
            EmrJobRunner(tmp.name, args.pyflink_runner_dir, args.external_job_config_bucket,
                         args.external_job_config_prefix, args.table_definition_path,
                         flink_cli_runner, jinja_template_resolver).run()
