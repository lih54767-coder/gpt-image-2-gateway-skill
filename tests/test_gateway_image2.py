"""Offline contract tests for the gateway-only Image 2 CLI."""
import base64
import io
import os
from pathlib import Path
import shutil
import stat
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gateway_image2 as g


def png(color=(255, 0, 0, 255), size=(1024, 1024)):
    image = Image.new('RGBA', size, color)
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


class Image2Contract(unittest.TestCase):
    def test_one_time_config_is_private_and_reused_without_env(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'IMAGE2_CONFIG_DIR': tmp, 'IMAGE2_SETUP_KEY': 'test-only-key'}, clear=True):
            self.assertEqual(g.main(['configure', '--base-url', 'https://one.example/v1', '--key-env', 'IMAGE2_SETUP_KEY']), 0)
            self.assertEqual(g._client().base_url.host, 'one.example')
            self.assertEqual(g._client().api_key, 'test-only-key')
            self.assertEqual(stat.S_IMODE((Path(tmp) / 'key').stat().st_mode), 0o600)
            self.assertNotIn('test-only-key', (Path(tmp) / 'config.json').read_text())
            os.environ.pop('IMAGE2_SETUP_KEY')
            self.assertEqual(g._client().api_key, 'test-only-key')
            self.assertEqual(g.main(['status']), 0)

    def test_unconfigured_no_implicit_real_or_openai_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'IMAGE2_CONFIG_DIR': tmp}, clear=True):
            with self.assertRaisesRegex(ValueError, 'configure'):
                g._client()
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                g.main(['configure', '--base-url', 'http://external.example/v1', '--key-env', 'MISSING'])
            self.assertFalse((Path(tmp) / 'config.json').exists())

    def test_separate_config_dirs_support_independent_agents(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for directory, host, key in ((first, 'first.example', 'first-key'), (second, 'second.example', 'second-key')):
                with patch.dict(os.environ, {'IMAGE2_CONFIG_DIR': directory, 'IMAGE2_TEST_KEY': key}, clear=True):
                    g.main(['configure', '--base-url', f'https://{host}/v1', '--key-env', 'IMAGE2_TEST_KEY'])
                    self.assertEqual(g._client().base_url.host, host)
                    self.assertEqual(g._client().api_key, key)

    def test_gateway_bundle_does_not_depend_on_upstream_image_gen_script(self):
        original = Path(__file__).resolve().parents[1] / 'scripts'
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('image_gen_gateway.py', 'gateway_image2.py', 'gateway_prompt.py'):
                shutil.copy2(original / name, Path(tmp) / name)
            result = subprocess.run([sys.executable, str(Path(tmp) / 'image_gen_gateway.py'), 'generate',
                                     '--prompt', 'a blue circle', '--dry-run'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_custom_dimensions_and_invalid_bounds(self):
        self.assertEqual(g.validate_size('2048x1152'), '2048x1152')
        self.assertEqual(g.validate_size('auto'), 'auto')
        for value in ('1000x1024', '512x512', '3840x3840', '1024x4096', '2048x512', 'oops'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                g.validate_size(value)

    def test_invalid_output_combinations_rejected(self):
        with self.assertRaises(ValueError):
            g.validate_output('transparent', 'jpeg', None)
        with self.assertRaises(ValueError):
            g.validate_output(None, 'png', 60)
        with self.assertRaises(ValueError):
            g.validate_output(None, 'webp', 101)
        self.assertEqual(g.validate_output('transparent', 'webp', 80), 'webp')

    def test_missing_or_malformed_response_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'bad.png'
            for raw in ('', '!!!!', base64.b64encode(b'not an image').decode()):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    g.save_images([raw], [target])
                self.assertFalse(target.exists())

    def test_gateway_png_response_converts_to_requested_webp_with_alpha(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'leaf.webp'
            b64 = base64.b64encode(png((0, 200, 0, 100))).decode()
            g.save_images([b64], [target], fmt='webp')
            with Image.open(target) as im:
                self.assertEqual(im.format, 'WEBP')
                self.assertIn('A', im.getbands())

    def test_valid_result_is_decoded_and_existing_file_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'ok.png'
            b64 = base64.b64encode(png()).decode()
            g.save_images([b64], [target])
            with Image.open(target) as image:
                self.assertEqual(image.size, (1024, 1024))
            with self.assertRaises(FileExistsError):
                g.save_images([b64], [target])
            self.assertEqual(target.read_bytes(), png())

    def test_count_mismatch_does_not_write_partial_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            targets = [Path(tmp) / f'{i}.png' for i in range(2)]
            with self.assertRaises(ValueError):
                g.save_images([base64.b64encode(png()).decode()], targets)
            self.assertTrue(all(not p.exists() for p in targets))

    def test_edit_mask_requires_alpha_and_equal_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.png'
            source.write_bytes(png())
            mask = root / 'mask.png'
            Image.new('RGB', (1024, 1024)).save(mask)
            with self.assertRaises(ValueError):
                g.validate_images([source], mask)
            Image.new('RGBA', (512, 512)).save(mask)
            with self.assertRaises(ValueError):
                g.validate_images([source], mask)
            Image.new('RGBA', (1024, 1024)).save(mask)
            g.validate_images([source], mask)

    def test_generate_dispatches_to_fixed_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'out.png'
            api = Mock()
            api.images.generate.return_value.data = [Mock(b64_json=base64.b64encode(png()).decode())]
            result = g.main(['generate', '--prompt', 'red circle', '--size', '2048x1152', '--out', str(target)], client=api)
            self.assertEqual(result, 0)
            self.assertTrue(target.exists())
            self.assertEqual(api.images.generate.call_args.kwargs['model'], 'gpt-image-2')
            self.assertEqual(api.images.generate.call_args.kwargs['size'], '2048x1152')

    def test_stream_requires_terminal_event_and_saves_optional_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            b64 = base64.b64encode(png()).decode()
            api = Mock()
            api.images.generate.return_value = iter([
                Mock(type='image_generation.partial_image', b64_json=b64),
                Mock(type='image_generation.completed', b64_json=b64),
            ])
            target = Path(tmp) / 'out.png'
            self.assertEqual(g.main(['generate', '--prompt', 'red circle', '--stream', '--partial-images', '1', '--out', str(target)], client=api), 0)
            self.assertTrue(target.exists())
            self.assertTrue((Path(tmp) / 'out-partial-1.png').exists())
            self.assertTrue(api.images.generate.call_args.kwargs['stream'])
            api.images.generate.return_value = iter([Mock(type='image_generation.partial_image', b64_json=b64)])
            with self.assertRaises(ValueError):
                g.main(['generate', '--prompt', 'red circle', '--stream', '--out', str(Path(tmp) / 'fail.png')], client=api)

    def test_images_stream_preview_written_before_completed_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            b64=base64.b64encode(png()).decode()
            target=Path(tmp)/'out.png'; preview=Path(tmp)/'out-partial-1.png'
            api=Mock()
            def events():
                yield Mock(type='image_generation.partial_image', b64_json=b64)
                self.assertTrue(preview.exists(), 'preview must appear during generation')
                yield Mock(type='image_generation.completed', b64_json=b64)
            api.images.generate.return_value=events()
            g.main(['generate','--prompt','red apple','--stream','--partial-images','1',
                    '--out',str(target)],client=api)

    def test_images_stream_preview_collision_is_preflight_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'out.png'; (Path(tmp)/'out-partial-1.png').write_bytes(b'keep')
            api=Mock()
            with self.assertRaises(FileExistsError):
                g.main(['generate','--prompt','red apple','--stream','--partial-images','1',
                        '--out',str(target)],client=api)
            api.images.generate.assert_not_called()

    def test_multiple_outputs_issue_individual_requests_and_save_complete_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = Mock()
            api.images.generate.return_value.data = [Mock(b64_json=base64.b64encode(png()).decode())]
            target = Path(tmp)/'series.png'
            self.assertEqual(g.main(['generate','--prompt','test','--n','2','--out',str(target)],client=api),0)
            self.assertEqual(api.images.generate.call_count,2)
            self.assertTrue(all(c.kwargs['n']==1 for c in api.images.generate.call_args_list))
            self.assertTrue((Path(tmp)/'series-1.png').exists())
            self.assertTrue((Path(tmp)/'series-2.png').exists())

    def test_failed_second_request_leaves_no_partial_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            api=Mock()
            api.images.generate.side_effect=[Mock(data=[Mock(b64_json=base64.b64encode(png()).decode())]),RuntimeError('upstream failed')]
            target=Path(tmp)/'series.png'
            with self.assertRaises(RuntimeError):
                g.main(['generate','--prompt','test','--n','2','--out',str(target)],client=api)
            self.assertFalse((Path(tmp)/'series-1.png').exists())

    def test_edit_dispatch_with_mask_and_two_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, reference, mask = root/'source.png', root/'ref.png', root/'mask.png'
            source.write_bytes(png()); reference.write_bytes(png((0, 0, 255, 255)))
            Image.new('RGBA', (1024, 1024), (255, 255, 255, 255)).save(mask)
            api = Mock()
            api.images.edit.return_value.data = [Mock(b64_json=base64.b64encode(png()).decode())]
            g.main(['edit', '--image', str(source), '--image', str(reference), '--mask', str(mask),
                    '--prompt', 'edit first with second', '--out', str(root/'result.png')], client=api)
            request = api.images.edit.call_args.kwargs
            self.assertEqual(len(request['image']), 2)
            self.assertEqual(request['model'], 'gpt-image-2')
            self.assertTrue(request['mask'].closed)

    def test_batch_jobs_dry_run_and_no_output_collisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = root/'jobs.jsonl'
            jobs.write_text('{"prompt":"red circle","size":"2048x1152","output_format":"webp"}\n')
            self.assertEqual(g.main(['generate-batch','--input',str(jobs),'--out-dir',str(root/'out'),'--dry-run']), 0)
            jobs.write_text('{"prompt":"a","out":"same.png"}\n{"prompt":"b","out":"same.png"}\n')
            with self.assertRaises(FileExistsError):
                g.main(['generate-batch','--input',str(jobs),'--out-dir',str(root/'out'),'--dry-run'])

    def test_multiple_edits_rewind_input_file_each_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.png';source.write_bytes(png())
            reads=[]
            api=Mock()
            def edit(**kwargs):
                reads.append(kwargs['image'].read())
                return Mock(data=[Mock(b64_json=base64.b64encode(png()).decode())])
            api.images.edit.side_effect=edit
            g.main(['edit','--image',str(source),'--prompt','make it blue','--n','2',
                    '--out',str(Path(tmp)/'out.png')],client=api)
            self.assertEqual(reads,[source.read_bytes(),source.read_bytes()])

    def test_responses_https_url_and_file_id_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            api=Mock();api.responses.create.return_value.output=[Mock(type='image_generation_call',result=base64.b64encode(png()).decode())]
            g.main(['tool','--prompt','combine','--image-url','https://example.org/ref.png',
                    '--file-id','file_sample','--out',str(Path(tmp)/'out.png')],client=api)
            contents=api.responses.create.call_args.kwargs['input'][0]['content']
            self.assertEqual(contents[1],{'type':'input_image','image_url':'https://example.org/ref.png'})
            self.assertEqual(contents[2],{'type':'input_image','file_id':'file_sample'})
            with self.assertRaises(ValueError):
                g.main(['tool','--prompt','test','--image-url','http://localhost/x.png',
                        '--out',str(Path(tmp)/'unused.png')],client=api)

    def test_legacy_prompt_augmentation_and_downscale_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            api=Mock();api.images.generate.return_value.data=[Mock(b64_json=base64.b64encode(png()).decode())]
            target=Path(tmp)/'original.png'
            g.main(['generate','--prompt','one red apple','--style','watercolor','--downscale-max-dim','100',
                    '--out',str(target)],client=api)
            prompt=api.images.generate.call_args.kwargs['prompt']
            self.assertIn('Primary request: one red apple',prompt)
            self.assertIn('Style/medium: watercolor',prompt)
            self.assertTrue((Path(tmp)/'original-web.png').exists())
            g.main(['generate','--prompt','red apple','--no-augment','--out',str(Path(tmp)/'plain.png')],client=api)
            self.assertEqual(api.images.generate.call_args.kwargs['prompt'],'red apple')

    def test_responses_stream_saves_partial_before_final_and_final_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'tool.png'
            preview=Path(tmp)/'tool-partial-0.png'
            b64=base64.b64encode(png()).decode()
            api=Mock()
            def events():
                yield Mock(type='response.image_generation_call.partial_image',
                           partial_image_index=0, partial_image_b64=b64)
                self.assertTrue(preview.exists(), 'partial must be available before completion')
                yield Mock(type='response.completed', response=Mock(id='resp_new',
                            output=[Mock(type='image_generation_call',result=b64)]))
            api.responses.create.return_value=events()
            self.assertEqual(g.main(['tool','--prompt','red apple','--stream','--partial-images','2',
                                     '--out',str(target)],client=api),0)
            self.assertTrue(target.exists())
            kwargs=api.responses.create.call_args.kwargs
            self.assertIs(kwargs['stream'],True)
            self.assertEqual(kwargs['tools'][0]['partial_images'],2)

    def test_responses_stream_rejects_existing_preview_before_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'tool.png'
            (Path(tmp)/'tool-partial-0.png').write_bytes(b'keep')
            api=Mock()
            with self.assertRaises(FileExistsError):
                g.main(['tool','--prompt','red apple','--stream','--partial-images','2',
                        '--out',str(target)],client=api)
            api.responses.create.assert_not_called()

    def test_responses_tool_uses_mainline_model_and_fixed_image_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            api=Mock()
            api.responses.create.return_value.output=[Mock(type='image_generation_call',result=base64.b64encode(png()).decode())]
            target=Path(tmp)/'tool.png'
            self.assertEqual(g.main(['tool','--prompt','draw red apple','--out',str(target)],client=api),0)
            request=api.responses.create.call_args.kwargs
            self.assertEqual(request['model'],'gpt-6-astra')
            self.assertEqual(request['tools'][0]['model'],'gpt-image-2')
            self.assertTrue(target.exists())

    def test_responses_tool_can_send_local_image_and_prior_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.png';source.write_bytes(png())
            api=Mock()
            api.responses.create.return_value.output=[Mock(type='image_generation_call',result=base64.b64encode(png()).decode())]
            g.main(['tool','--prompt','add leaf','--image',str(source),'--action','edit',
                    '--previous-response-id','resp_previous','--out',str(Path(tmp)/'out.png')],client=api)
            request=api.responses.create.call_args.kwargs
            self.assertEqual(request['tools'][0]['action'],'edit')
            self.assertEqual(request['previous_response_id'],'resp_previous')
            self.assertTrue(request['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,'))

    def test_previous_response_id_without_explicit_image_fails_before_api_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            api=Mock()
            with self.assertRaisesRegex(ValueError,'--image'):
                g.main(['tool','--prompt','make it green','--action','edit',
                        '--previous-response-id','resp_old','--out',str(Path(tmp)/'out.png')], client=api)
            api.responses.create.assert_not_called()

    def test_responses_without_image_result_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            api=Mock();api.responses.create.return_value.output=[Mock(type='message',result=None)]
            target=Path(tmp)/'out.png'
            with self.assertRaises(ValueError):
                g.main(['tool','--prompt','test','--out',str(target)],client=api)
            self.assertFalse(target.exists())

    def test_gateway_entrypoint_accepts_image2_custom_size(self):
        wrapper = Path(__file__).resolve().parents[1] / 'scripts/image_gen_gateway.py'
        run = subprocess.run([sys.executable, str(wrapper), 'generate', '--prompt', 'test',
                              '--size', '2048x1152', '--dry-run'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('2048x1152', run.stdout)

    def test_unrecognized_model_and_input_fidelity_fail_closed(self):
        for extra in (['--model', 'gpt-image-1'], ['--input-fidelity', 'low']):
            with self.subTest(extra=extra), self.assertRaises(SystemExit):
                g.main(['generate', '--prompt', 'x', *extra], client=Mock())


if __name__ == '__main__':
    unittest.main()
