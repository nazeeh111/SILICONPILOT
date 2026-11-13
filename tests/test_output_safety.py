import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (ROOT / 'models/banknote_4x8x2.json').read_bytes()
ENV = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'src'))
from siliconpilot.model import HardwareConfig


def first_candidate():
    cfg = HardwareConfig(bits=4, fractional_bits=1, accumulator_bits=16,
                         parallelism=1, pipeline=False)
    return 'live-' + hashlib.sha256(json.dumps(cfg.to_dict(), sort_keys=True).encode()).hexdigest()[:10]


class OutputSafetyTests(unittest.TestCase):
    def run_cli(self, command, model, output, *extra):
        return subprocess.run(['python3', '-m', 'siliconpilot.cli', command,
                               str(model), '--out', str(output), *map(str, extra)],
                              env=ENV, capture_output=True, text=True)

    def test_same_directory_and_aliases_refuse_before_any_output(self):
        for command in ('compile', 'verify', 'build'):
            for case in ('inside', 'hardlink', 'symlink'):
                with self.subTest(command=command, case=case), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    out = root / 'out'
                    out.mkdir()
                    source = (out if case == 'inside' else root) / 'weights.json'
                    source.write_bytes(FIXTURE)
                    sentinel = out / 'design.v'
                    sentinel.write_bytes(b'keep')
                    if case == 'hardlink':
                        os.link(source, out / 'weights.json')
                    if case == 'symlink':
                        (out / 'weights.json').symlink_to(source)
                    result = self.run_cli(command, source, out)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(source.read_bytes(), FIXTURE)
                    self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_config_alias_refused_without_output_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'out'
            out.mkdir()
            model = root / 'model.json'
            model.write_bytes(FIXTURE)
            config = root / 'config.json'
            config.write_text('{}')
            (out / 'manifest.json').symlink_to(config)
            result = self.run_cli('compile', model, out, '--config', config)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(config.read_text(), '{}')
            self.assertFalse((out / 'design.v').exists())

    def test_existing_unrelated_output_can_be_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / 'model.json'
            model.write_bytes(FIXTURE)
            out = root / 'out'
            out.mkdir()
            (out / 'design.v').write_text('old')
            result = self.run_cli('compile', model, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual((out / 'design.v').read_text(), 'old')
            self.assertEqual(model.read_bytes(), FIXTURE)

    def test_non_generated_input_in_output_directory_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            model = out / 'my-model.json'
            model.write_bytes(FIXTURE)
            result = self.run_cli('compile', model, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(model.read_bytes(), FIXTURE)

    def test_later_verify_and_build_outputs_checked_before_first_write(self):
        for command, name in (('verify', 'inputs.hex'), ('build', 'routed.config')):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                model = out / name
                model.write_bytes(FIXTURE)
                result = self.run_cli(command, model, out)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(model.read_bytes(), FIXTURE)
                self.assertFalse((out / 'design.v').exists())

    def test_dataset_input_alias_refused_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            out = root / 'out'
            out.mkdir()
            model = root / 'model.json'
            model.write_bytes(FIXTURE)
            dataset = root / 'data/banknote.csv'
            dataset.write_bytes(b'keep')
            os.link(dataset, out / 'inputs.hex')
            result = subprocess.run(['python3', '-m', 'siliconpilot.cli', '--root', str(root),
                                     'verify', str(model), '--out', str(out), '--dataset'],
                                    env=ENV, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(dataset.read_bytes(), b'keep')
            self.assertFalse((out / 'design.v').exists())

    def test_replay_rejects_all_corpus_output_aliases(self):
        for name in ('surrogate.joblib', 'surrogate_metadata.json', 'experiments.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                out = root / 'out'
                out.mkdir()
                corpus = root / 'corpus.json'
                corpus.write_text('[]')
                os.link(corpus, out / name)
                result = subprocess.run(['python3', '-m', 'siliconpilot.cli', 'replay',
                                         '--corpus', str(corpus), '--out', str(out)],
                                        env=ENV, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(corpus.read_text(), '[]')
                self.assertEqual(len(list(out.iterdir())), 1)

    def test_search_rejects_top_level_and_candidate_aliases(self):
        names = ('live-search.json.tmp', first_candidate() + '/weights.json',
                 first_candidate() + '/verification.json', first_candidate() + '/routing.json')
        for name in names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                out = root / 'out'
                destination = out / name
                destination.parent.mkdir(parents=True)
                model = root / 'model.json'
                model.write_bytes(FIXTURE)
                os.link(model, destination)
                result = self.run_cli('search', model, out)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(model.read_bytes(), FIXTURE)
                self.assertFalse((out / 'live-search.json.tmp').exists() and name != 'live-search.json.tmp')

    def test_search_replace_rejects_direct_and_symlink_chain_input_paths(self):
        for case in ('direct', 'symlink', 'symlink_chain'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                out = root / 'out'
                out.mkdir()
                target = out / 'live-search.json'
                if case == 'symlink_chain':
                    backing = root / 'backing.json'
                    backing.write_bytes(FIXTURE)
                    target.symlink_to(backing)
                else:
                    target.write_bytes(FIXTURE)
                model = target
                if case != 'direct':
                    model = root / 'model-link.json'
                    model.symlink_to(target)
                result = self.run_cli('search', model, out)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(model.read_bytes(), FIXTURE)
                self.assertFalse((out / 'live-search.json.tmp').exists())

    def test_search_replace_allows_separate_hardlink_and_target_symlink(self):
        from siliconpilot import cli
        fake = types.ModuleType('siliconpilot.search')
        fake.Budgets = lambda **kwargs: kwargs
        fake.run_experiments = lambda *args, **kwargs: {}
        fake.optimize = lambda *args, **kwargs: {'mode': 'search'}
        for case in ('hardlink', 'target_symlink'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                out = root / 'out'
                out.mkdir()
                model = root / 'model.json'
                model.write_bytes(FIXTURE)
                target = out / 'live-search.json'
                if case == 'hardlink':
                    os.link(model, target)
                else:
                    target.symlink_to(model)
                with patch.dict(sys.modules, {'siliconpilot.search': fake}), \
                     patch.object(sys, 'argv', ['siliconpilot', 'search', str(model), '--out', str(out)]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    cli.main()
                self.assertEqual(model.read_bytes(), FIXTURE)

    def test_shared_candidate_ids_match_previous_algorithm(self):
        from siliconpilot.search_identity import live_candidate_id
        for bits in (4, 6, 8):
            for lanes in (1, 2, 4):
                for pipeline in (False, True):
                    cfg = HardwareConfig(bits=bits, fractional_bits=bits-3,
                                         accumulator_bits=2*bits+8, parallelism=lanes, pipeline=pipeline)
                    expected = 'live-' + hashlib.sha256(json.dumps(cfg.to_dict(), sort_keys=True).encode()).hexdigest()[:10]
                    self.assertEqual(live_candidate_id(cfg), expected)

    def test_search_rejects_validation_and_default_dataset_aliases(self):
        for case in ('validation', 'dataset', 'manifest'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                out = root / 'out'
                out.mkdir()
                model = root / 'model.json'
                model.write_bytes(FIXTURE)
                if case == 'validation':
                    source = root / 'validation.json'
                elif case == 'dataset':
                    source = root / 'data/banknote.csv'
                else:
                    source = root / 'models/dataset_manifest.json'
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('original')
                (out / 'live-search.json.tmp').symlink_to(source)
                cmd = ['python3', '-m', 'siliconpilot.cli', '--root', str(root),
                       'search', str(model), '--out', str(out)]
                if case == 'validation':
                    cmd.extend(['--validation-data', str(source)])
                result = subprocess.run(cmd, env=ENV, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(source.read_text(), 'original')

    def test_search_checks_symlinked_candidate_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'out'
            out.mkdir()
            external = root / 'external'
            external.mkdir()
            model = root / 'model.json'
            model.write_bytes(FIXTURE)
            os.link(model, external / 'weights.json')
            (out / first_candidate()).symlink_to(external, target_is_directory=True)
            result = self.run_cli('search', model, out)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(model.read_bytes(), FIXTURE)
            self.assertFalse((out / 'live-search.json.tmp').exists())

    def test_netlist_rejects_cross_input_aliases(self):
        for case in ('hardlink', 'symlink'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                source = out / 'build.json'
                source.write_text('original')
                sim = out / 'netlist-check'
                sim.mkdir()
                target = sim / 'expected.hex'
                if case == 'hardlink':
                    os.link(source, target)
                else:
                    target.symlink_to(source)
                result = subprocess.run(['python3', '-m', 'siliconpilot.cli', 'netlist', str(out)],
                                        env=ENV, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(source.read_text(), 'original')
                self.assertFalse((out / 'netlist-verification.json').exists())

    def test_netlist_allows_existing_unrelated_output(self):
        from siliconpilot import cli
        fake = types.ModuleType('siliconpilot.netlist')
        calls = []
        fake.prepare_logic_only_build = lambda *args, **kwargs: None
        fake.run_netlist_verification = lambda directory: calls.append(directory) or {'passed': True}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'build.json').write_text('original')
            sim = out / 'netlist-check'
            sim.mkdir()
            (sim / 'expected.hex').write_text('old output')
            with patch.dict(sys.modules, {'siliconpilot.netlist': fake}), \
                 patch.object(sys, 'argv', ['siliconpilot', 'netlist', str(out)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                cli.main()
            self.assertEqual(calls, [out])
            self.assertEqual((out / 'build.json').read_text(), 'original')

    def test_train_rejects_dataset_output_alias(self):
        for name in ('banknote_4x4x2.json', 'banknote_4x8x2.json',
                     'banknote_4x12x2.json', 'dataset_manifest.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'data').mkdir()
                (root / 'models').mkdir()
                source = root / 'data/banknote.csv'
                source.write_text('original')
                os.link(source, root / 'models' / name)
                result = subprocess.run(['python3', '-m', 'siliconpilot.cli', '--root', str(root), 'train'],
                                        env=ENV, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(source.read_text(), 'original')

    def test_train_allows_unrelated_existing_outputs(self):
        from siliconpilot import cli
        fake = types.ModuleType('siliconpilot.dataset')
        calls = []
        fake.train_models = lambda root: calls.append(root) or {'trained': True}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'models').mkdir()
            (root / 'data/banknote.csv').write_text('original')
            (root / 'models/banknote_4x4x2.json').write_text('old output')
            with patch.dict(sys.modules, {'siliconpilot.dataset': fake}), \
                 patch.object(sys, 'argv', ['siliconpilot', '--root', str(root), 'train']), \
                 contextlib.redirect_stdout(io.StringIO()):
                cli.main()
            self.assertEqual(calls, [root])

    def test_replace_preserves_hardlinked_target_but_tmp_write_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.write_text('original')
            target = root / 'live-search.json'
            os.link(source, target)
            staging = root / 'live-search.json.tmp'
            staging.write_text('new result')
            staging.replace(target)
            self.assertEqual(source.read_text(), 'original')
            self.assertEqual(target.read_text(), 'new result')
            os.link(source, staging)
            staging.write_text('truncated')
            self.assertEqual(source.read_text(), 'truncated')

    def test_search_and_replay_accept_safe_input_inside_output(self):
        from siliconpilot import cli
        fake = types.ModuleType('siliconpilot.search')
        fake.Budgets = lambda **kwargs: kwargs
        fake.optimize = lambda *args, **kwargs: {'mode': 'search'}
        fake.run_experiments = lambda *args, **kwargs: {'mode': 'replay'}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            model = out / 'my-model.json'
            model.write_bytes(FIXTURE)
            corpus = out / 'my-corpus.json'
            corpus.write_text('[]')
            for argv in (['siliconpilot', 'search', str(model), '--out', str(out)],
                         ['siliconpilot', 'replay', '--corpus', str(corpus), '--out', str(out)]):
                with self.subTest(command=argv[1]), patch.dict(sys.modules, {'siliconpilot.search': fake}), \
                     patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                    cli.main()
            self.assertEqual(model.read_bytes(), FIXTURE)
            self.assertEqual(corpus.read_text(), '[]')


if __name__ == '__main__':
    unittest.main()
