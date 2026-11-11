"""Verifica este respaldo por lectura, sin red ni dependencias externas."""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import stat
import struct
import sys

PIN = {'payload_sha256': 'cc7bf44b54a9309d67e52d77cf7e41fd5e4cd7063168dfc70ffd57785ba7657d', 'provenance_sha256': '390dc2a8c1f267e908027f0efb348be3139ca9a222f162d7dd5439309aa8b117', 'P0_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'P2_closure_sha256': '92c36815a7922e553299b164d657493d9bf33340cfafc46a778c7bcd6ff71b37', 'source_commit': '323fda951c74099fa92602b7ada634542b967ee3', 'parent': {'version': 'gold-a-769a847f096b', 'payload_sha256': '769a847f096bba8a5a7269c34ddc780ca7dc35d170fde128b871fda019ebe6c8', 'manifest_sha256': '7d319bc64ba2702d1bd11dd7bb10ae4525b5e3bd392b58d09a860af73e9f3a9c'}, 'profile': {'context_tokens': 2048, 'dimension': 768, 'model': 'embeddinggemma:latest', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'name': 'documentary_A', 'ollama_version': '0.40.13', 'recipe_source_sha256': 'ce71bedba019d7cd54952a22fb2973fc462924f6549baec808c6f059ea531739', 'request_keys': ['model', 'prompt'], 'request_path': '/api/embeddings', 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'identity': {'schema_version': 1, 'kind': 'not_loaded', 'manifest_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'context_tokens': 2048, 'dimension': 768, 'model': 'embeddinggemma:latest', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'name': 'documentary_A', 'ollama_version': '0.40.13', 'recipe_source_sha256': 'ce71bedba019d7cd54952a22fb2973fc462924f6549baec808c6f059ea531739', 'request_keys': ['model', 'prompt'], 'request_path': '/api/embeddings', 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}, 'source_commit': '323fda951c74099fa92602b7ada634542b967ee3', 'HEAD': '323fda951c74099fa92602b7ada634542b967ee3', 'main': '23c6c5bab2e4b47dbda77f3d197ce46dab2af57a', 'records': 5862, 'reused_A': 5852, 'new_A': 10, 'parent': {'version': 'gold-a-769a847f096b', 'payload_sha256': '769a847f096bba8a5a7269c34ddc780ca7dc35d170fde128b871fda019ebe6c8', 'manifest_sha256': '7d319bc64ba2702d1bd11dd7bb10ae4525b5e3bd392b58d09a860af73e9f3a9c'}, 'Chroma_operations': False, 'distance_for_new_collection': 'cosine'}, 'records_sha256': 'a27f853b8d81bdaedc0a8a947a9cdf8e160ba19c7b52b3fd93368490aa269a2b', 'ids_sha256': '5d539241aafd995b11af576c0fd338f9dbb0b30a8cb07d7e8332d4a4c147aede', 'reuse_sha256': '32a953bc0d48e57ffd32781180d7e9270ac63dbe0ed779d1b3b393aab0b57810', 'gold_files_sha256': '912f13c5335233e6ce01ce9b629a86baee632fa5dc415ef05054b7e672394c14', 'new_inputs': [{'id': 'AP Inversiones E y D S.A.S VS DIMAR y otros_s2_c20', 'input_sha256': '4308f69dd9af02b5096fdde2dde0c512b3f7db3669c1ccbdbb175fa1f0d4429a'}, {'id': 'CE_2da_AP_2010_028_Radley_Bent_VS_Dimar_Daños_Ambientales_Embarcaciones_s1_c2', 'input_sha256': '1e677ea64137f2e611a777a64b738e48874a3bda973d152addfb3f9cf649d785'}, {'id': 'CE_2da_AP_2010_028_Radley_Bent_VS_Dimar_Daños_Ambientales_Embarcaciones_s3_c37', 'input_sha256': '3d69040e3f51fd36c8209a449df580dd77fe76f61a86c20cf8f64a343f233d05'}, {'id': 'CE_2da_AP_2016_328_Ricardo_Cabrales_VS_Mun_Coveñas_Playa_Uso_Publico_s3_c50', 'input_sha256': '96dd4ba481f31f1e1c56427de611667ab203d7aa9fa74088324beca42faf4160'}, {'id': 'CE_2da_NYR_1994_993_Inversiones_Araujo_VS_Capitania_Puerto_Cartagena_Urbanismo_Playa_s2_c2', 'input_sha256': 'c358db53334d0cb988d1a136993f7bf002a6a6db33bfcb16bfc00be7435cfdd6'}, {'id': 'CE_2da_NYR_1998_102_Flury_Valencia_VS_MinDefensa_Uso_Urbanistico_Playa_s3_c28', 'input_sha256': '39381d3ef18f3e2b2daeb57f72a265519b92657b4787e2d75ee369aa57da4454'}, {'id': 'CE_Consulta_2010_071_MinAmbiente_Bienes_De_Uso_Publico_s3_c4', 'input_sha256': 'e163d6fe657d4f60e1dcf456d1ad22c813bb343c0b0cedb976facd2e6d823465'}, {'id': 'decreto-2324-de-1984_s170_art169_c0', 'input_sha256': 'b89a35b8a1a8cb913a409abf3e9894666a9d428341c0bbe9a96b68da414bf240'}, {'id': 'decreto-2324-de-1984_s170_art169_c1', 'input_sha256': '748ffa8ec6f68e01cc554c41b985539722316749cb604961e7f5a74284b5ca95'}, {'id': 'decreto-2324-de-1984_s170_art169_c2', 'input_sha256': '4e9bbd0fdc327a8ef0cd1aa9085ca8e6d8059534fe2eb28f57421ed0e175f4f0'}], 'new_vectors': {'AP Inversiones E y D S.A.S VS DIMAR y otros_s2_c20': {'kind': 'P2_accepted_result', 'input_sha256': '4308f69dd9af02b5096fdde2dde0c512b3f7db3669c1ccbdbb175fa1f0d4429a', 'vector_sha256': '910049c10094e03ebcb94926f2c7f99ec2398e1ed8a5f6c1ec811af161c424ca', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 3, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': 'd52c18af6c0a6ce7bd9022c71458e6616211762e29e39401c0bec615bebcc3aa', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': '85244987915c1c375afa9192d7816d6107851f1f971a735e2c04940b25e0ce2c'}, 'tokens': 209}, 'CE_2da_AP_2010_028_Radley_Bent_VS_Dimar_Daños_Ambientales_Embarcaciones_s1_c2': {'kind': 'P2_accepted_result', 'input_sha256': '1e677ea64137f2e611a777a64b738e48874a3bda973d152addfb3f9cf649d785', 'vector_sha256': '8a6c203b5acf2bc493eba8d80404b8c92ab104da6ecb19024a1e0c0517e0582e', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 5, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': 'af95212cecfd8db5ad09cfb0f0b2f655c8d6d7802a33a65b18594496a1b9f086', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': 'e44852bbe2a7fec8994dd0743026d601c73a3c1c73d83f52af123078d26079ec'}, 'tokens': 345}, 'CE_2da_AP_2010_028_Radley_Bent_VS_Dimar_Daños_Ambientales_Embarcaciones_s3_c37': {'kind': 'P2_accepted_result', 'input_sha256': '3d69040e3f51fd36c8209a449df580dd77fe76f61a86c20cf8f64a343f233d05', 'vector_sha256': 'e5dd1870a3aa75744c923b2f976069cb327df95531eb6affade206d69daa0c69', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 7, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': '0647ede7dd28e581bdc2f18e8f61661c91a23fd6cecbb63d16abb184af14fba2', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': 'b37ff5cd2e24ef72d678df16c5bf7b3f0753942e68199ceda59213248472bc56'}, 'tokens': 320}, 'CE_2da_AP_2016_328_Ricardo_Cabrales_VS_Mun_Coveñas_Playa_Uso_Publico_s3_c50': {'kind': 'P2_accepted_result', 'input_sha256': '96dd4ba481f31f1e1c56427de611667ab203d7aa9fa74088324beca42faf4160', 'vector_sha256': '490bb210d8285d11d48683b9aa8f34c0d6524cc654b290c20a01cb04ed6e07d9', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 9, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': 'd9f0e4217e8ab3f27140019a9130f8fc9adbeab910883168e50c020e30587e17', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': 'c6167f60c181be672cd655c9d440be36997d7cff80666012a06b7b78218d4523'}, 'tokens': 295}, 'CE_2da_NYR_1994_993_Inversiones_Araujo_VS_Capitania_Puerto_Cartagena_Urbanismo_Playa_s2_c2': {'kind': 'P2_accepted_result', 'input_sha256': 'c358db53334d0cb988d1a136993f7bf002a6a6db33bfcb16bfc00be7435cfdd6', 'vector_sha256': '42e7853e02f2c128281075edc947be09c8fbeaa21e25e6d1a32b5812a77ae5cd', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 11, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': '3b98d0c999815b73ffa04ab11fa9c5f7aba6beb74e89ae3a8e50ee9807a8eb63', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': '3dfc8c4924556b786032d4c7d2f46c891ece7bdc8be3ce525fd7611553e9da4a'}, 'tokens': 407}, 'CE_2da_NYR_1998_102_Flury_Valencia_VS_MinDefensa_Uso_Urbanistico_Playa_s3_c28': {'kind': 'P2_accepted_result', 'input_sha256': '39381d3ef18f3e2b2daeb57f72a265519b92657b4787e2d75ee369aa57da4454', 'vector_sha256': '14594b1fb2785070be388d8b7e3da85be17167a27c448a59fc971689f4e3f846', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 13, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': 'de276d42ce1d8f69d74b557b41c64d9bcd55382c2f62aab25d9c794fbf885e6f', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': 'f6532c7a27271f79e1a12d9407caff10a308f70dda0a58a8ed691498e23d3bfe'}, 'tokens': 363}, 'CE_Consulta_2010_071_MinAmbiente_Bienes_De_Uso_Publico_s3_c4': {'kind': 'P2_accepted_result', 'input_sha256': 'e163d6fe657d4f60e1dcf456d1ad22c813bb343c0b0cedb976facd2e6d823465', 'vector_sha256': 'b1257a5ba2c51dd1e59e6af6cfe006432e250a753e9c9cedbdd06f8146b86c87', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 15, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': '99952db5047e9a27aef9249877c8a581f5e1637f6afe34ec29d1c27ae5af9ae9', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': '61e1e3cb5f9e36d981bb52d2485d895079ce77b8a436024b55e5ac4579e19294'}, 'tokens': 268}, 'decreto-2324-de-1984_s170_art169_c0': {'kind': 'P2_accepted_result', 'input_sha256': 'b89a35b8a1a8cb913a409abf3e9894666a9d428341c0bbe9a96b68da414bf240', 'vector_sha256': '2e4174569300841af6115dbd4f055d92341764305896d28ddcbb7e5ae59d1e04', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 17, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': '36997b46b39026d7115e60c6469cdbf6a4774bef37435f00ad262ce0ba57cebe', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': 'e16fc327a378d249864e3c8f391c66c93f020af30d1bb319d4f7abb508e3668c'}, 'tokens': 352}, 'decreto-2324-de-1984_s170_art169_c1': {'kind': 'P2_accepted_result', 'input_sha256': '748ffa8ec6f68e01cc554c41b985539722316749cb604961e7f5a74284b5ca95', 'vector_sha256': '0a93d330f5cf256a29169b991f3599adb66bccecf97565fcb071f5bbc801f09c', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 19, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': 'a80d664fa75054277f80c0dcfcc11192bf9bbb85d101a55331ee3a7f40716105', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': '1100328732ef9cfb1f360d796ec0d5d4804097ef27380b49c21bdf740061d2c4'}, 'tokens': 327}, 'decreto-2324-de-1984_s170_art169_c2': {'kind': 'P2_accepted_result', 'input_sha256': '4e9bbd0fdc327a8ef0cd1aa9085ca8e6d8059534fe2eb28f57421ed0e175f4f0', 'vector_sha256': '49800c13847e45dfc8e350658a5bb0c3b63e5e794f57620d09d7f39f0c1870bc', 'journal_sha256': '94543ac493dc645ee090f9f8be5318a7737513add633d931e9e37bf57455aef9', 'journal_line': 21, 'generation_receipt_sha256': 'fe1bffee521d67b22ddfc17bec424944e85c518be8891faecc3c36d24b948a02', 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc', 'worker_stdout_sha256': '33abe2006e766fbc91fe1c9e76e7e75941c7baf8244e0e1237cb9bfa7b161971', 'accepted_receipt': {'final': {'container_identity': [1106, 1287], 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'ready': {'base_sha256': 'fa6c6b43a0e55fd47ed48d8f793e92a1b937bd33d90ea7073faf1a0928df943c', 'container_identity': [1106, 1287], 'dimension': 768, 'kind': 'ready', 'model_blob_sha256': '0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515', 'model_digest': '85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1', 'ollama_version': '0.40.13', 'profile_sha256': 'f855fcd94537c658242b40a21a89eb1d02479a7c199748287d363e023eb2c1e3', 'runner_identity': [7316, 638577], 'runtime_arguments': {'batch': 2048, 'ctx_total': 2048, 'microbatch': 2048, 'parallel': 1}}, 'worker_reply_sha256': '605a042d55f558576b90420afcf62a465f192b7777687999f245ef67342481c0'}, 'tokens': 194}}, 'duplicate_groups': [{'vector_sha256': '01ff8263f0f53b3ea67bbb63b9a515521c3435742398d4af17e3b1763b10e464', 'ids': ['CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c31__part2', 'SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c31__part2']}, {'vector_sha256': '3e337fd6c7703d3918f759dfef3c078cb97aeffb9d7416acbd25618124aa3976', 'ids': ['CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c99__part1', 'SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c99__part1']}, {'vector_sha256': '616298ec5b739b75a399e166c09e4b082a379ed3fe77272978cb65ce5e70a01f', 'ids': ['CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c31__part1', 'SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c31__part1']}], 'historical_duplicate_pairs': [{'ids': ['CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c31__part1', 'SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c31__part1'], 'vector_sha256': '616298ec5b739b75a399e166c09e4b082a379ed3fe77272978cb65ce5e70a01f'}, {'ids': ['CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c31__part2', 'SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c31__part2'], 'vector_sha256': '01ff8263f0f53b3ea67bbb63b9a515521c3435742398d4af17e3b1763b10e464'}, {'ids': ['CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera_s4_c99__part1', 'SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO_s4_c99__part1'], 'vector_sha256': '3e337fd6c7703d3918f759dfef3c078cb97aeffb9d7416acbd25618124aa3976'}], 'payload_changes': 11, 'token_counts': {'scope': 'ten_new_inputs_only', 'records': 10, 'min_tokens': 194, 'max_tokens': 407, 'total_tokens': 3080, 'limit_including_specials': 2048, 'token_options': {'add_special': True, 'parse_special': True, 'with_pieces': False}, 'counts_receipt_sha256': '34b2b298a6b4b6509e4ee1ccb53bfb46db051bf60b091be201462735ac578dbc'}}
FILES = {"GOLD_A.jsonl.gz", "PROCEDENCIA_GOLD_A.json", "manifest.json",
         "README.md", "verificar_paquete.py"}


def require(ok, category):
    if not ok:
        raise ValueError(category)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "duplicate_json_key")
            out[key] = value
        return out
    def finite(text):
        value = float(text)
        require(math.isfinite(value), "nonfinite_json")
        return value
    def reject(_):
        raise ValueError("nonfinite_json")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=finite,
                      parse_constant=reject)


def _build_embedding_text(text: str, meta: dict[str, Any]) -> str:
    """
    Construye el texto aumentado para embedding combinando metadatos clave
    con el contenido del chunk (Contextual Chunk Headers).

    El vector resultante captura tanto el contenido semántico como el
    contexto documental (sección, tema, keywords, resumen). El texto
    original se almacena por separado en ChromaDB para que el LLM lo reciba limpio.
    """
    parts: list[str] = []
    if meta.get("doc_type") == "normativa":
        norma = meta.get("title") or meta.get("norma")
        articulo = meta.get("articulo")
        if norma and articulo:
            parts.append(f"Norma: {norma} — Artículo {articulo}")
        elif norma:
            parts.append(f"Norma: {norma}")
        elif articulo:
            parts.append(f"Artículo {articulo}")
    if kw := meta.get("keywords_str", ""):
        parts.append(f"Palabras clave: {kw}")
    if summary := meta.get("summary", ""):
        parts.append(f"Resumen: {summary}")
    if parts:
        return "\n".join(parts) + "\n\n" + text
    return text


def validate_vector(vector):
    require(type(vector) is list and len(vector) == 768, "vector_dimension")
    require(all(type(v) in (int, float) and math.isfinite(v) for v in vector),
            "vector_number")
    require(math.isfinite(math.hypot(*vector)) and math.hypot(*vector) > 0,
            "vector_norm")
    rounded = struct.unpack("<768f", struct.pack("<768f", *vector))
    require(all(math.isfinite(v) for v in rounded) and math.hypot(*rounded) > 0,
            "vector_float32")
    return sha(canonical(vector))


def verify_package(root):
    require(root.is_dir() and not root.is_symlink(), "package_directory")
    require({p.name for p in root.iterdir()} == FILES, "package_files")
    for name in FILES:
        path = root / name
        require(not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode)
                and path.resolve().parent == root.resolve(), "package_file_type")
    manifest = strict_json((root / "manifest.json").read_bytes())
    require(manifest["schema_version"] == 1
            and manifest["kind"] == "gold_logical_input_backup"
            and manifest["version"] == "gold-a-" + PIN["payload_sha256"][:12],
            "manifest_identity")
    require(manifest["files"].keys() == FILES - {"manifest.json"}, "file_list")
    for name, entry in manifest["files"].items():
        require(set(entry) == {"sha256", "bytes", "preparation_mode"}
                and type(entry["bytes"]) is int and entry["bytes"] > 0
                and entry["preparation_mode"] == 0o600, "file_entry")
        path = root / name
        require(path.stat().st_size == entry["bytes"]
                and file_hash(path) == entry["sha256"], "file_integrity")
    require(file_hash(root / "GOLD_A.jsonl.gz") == PIN["payload_sha256"]
            and file_hash(root / "PROCEDENCIA_GOLD_A.json") == PIN["provenance_sha256"],
            "pinned_data_hashes")
    identity = manifest["content"]["payload_manifest"]
    require(identity == PIN["identity"], "payload_identity")
    require(manifest["source"]["source_gold_commit"] == PIN["source_commit"]
            and manifest["source"]["main"] == PIN["identity"]["main"]
            and manifest["source"]["Gold_P0_sha256"] == PIN["P0_sha256"]
            and manifest["source"]["parent"] == PIN["parent"]
            and sha(canonical(manifest["source"]["gold_files"])) == PIN["gold_files_sha256"],
            "source_contract")
    require(manifest["embedding"] == PIN["profile"], "embedding_profile")
    require(manifest["state_at_packaging"] == {
        "generation_verified": True, "package_imported": False,
        "independent_restore_tested": False, "activated": False,
        "durability_tested": False, "remote_state_rechecked_at_packaging": False},
        "state_contract")
    require(manifest["readback_contract"]["verified"] is False
            and manifest["readback_contract"]["universal_across_builds"] is False,
            "readback_not_verified")
    require(manifest["index"] == {"recommended_space": "cosine",
                                  "configuration_verified": False}, "index_not_verified")
    require(manifest["evidence"]["P2_closure_sha256"] == PIN["P2_closure_sha256"]
            and manifest["evidence"]["full_forensic_chain_included"] is False,
            "evidence_contract")
    new_origin = next(iter(PIN["new_vectors"].values()))
    require(all(manifest["evidence"][key] == new_origin[key] for key in (
        "counts_receipt_sha256", "generation_receipt_sha256", "journal_sha256")),
        "evidence_receipt_hashes")
    require(manifest["content"]["payload_changes"] == PIN["payload_changes"],
            "payload_change_count")
    sidecar = strict_json((root / "PROCEDENCIA_GOLD_A.json").read_bytes())
    require(sidecar["identity"] == identity and sidecar["partial_sources"] == [],
            "provenance_identity")
    refs = sidecar["vector_records"]
    require(type(refs) is list and len(refs) == 5862
            and len({r["id"] for r in refs}) == 5862, "provenance_coverage")
    sources = {r["path"]: r for r in manifest["source"]["gold_files"]}
    records, ids, reused, new = [], [], [], []
    kinds, vectors, vector_ids = Counter(), Counter(), defaultdict(list)
    with gzip.open(root / "GOLD_A.jsonl.gz", "rb") as stream:
        require(strict_json(stream.readline()) == {"__manifest__": identity},
                "gzip_header")
        for index, line in enumerate(stream):
            require(index < 5862 and line.endswith(b"\n"), "gzip_rows")
            row = strict_json(line)
            require(type(row) is dict
                    and set(row) == {"id", "document", "metadata", "embedding"},
                    "record_fields")
            ident, body, meta = row["id"], row["document"], row["metadata"]
            require(type(ident) is str and bool(ident)
                    and type(body) is str and bool(body.strip())
                    and type(meta) is dict and meta.get("chunk_id") == ident,
                    "record_identity")
            require(all(type(k) is str and k and type(v) in (str, int, float, bool)
                        and (type(v) is not float or math.isfinite(v))
                        for k, v in meta.items()), "metadata_scalar")
            require(meta.get("doc_type") in ("jurisprudencia", "normativa"), "doc_type")
            ref = refs[index]
            require(ref["id"] == ident, "provenance_order")
            content_hash, metadata_hash = sha(body.encode("utf-8")), sha(canonical(meta))
            input_hash = sha(_build_embedding_text(body, meta).encode("utf-8"))
            vector_hash = validate_vector(row["embedding"])
            require((ref["page_content_sha256"], ref["metadata_payload_sha256"],
                     ref["embedding_input_sha256"], ref["vector_sha256"]) ==
                    (content_hash, metadata_hash, input_hash, vector_hash), "record_hashes")
            doc, origin = ref["document_source"], ref["vector_source"]
            require(doc["commit"] == PIN["source_commit"]
                    and doc["path"] in sources
                    and doc["file_sha256"] == sources[doc["path"]]["sha256"]
                    and type(doc["line"]) is int and doc["line"] > 0,
                    "document_source")
            if ref["origin"] == "reused_parent":
                require(origin["kind"] == "parent_package"
                        and origin["package"] == PIN["parent"]
                        and origin["id"] == ident and origin["vector_sha256"] == vector_hash
                        and origin["embedding_input_sha256"] == input_hash
                        and type(origin["line"]) is int and origin["line"] >= 2,
                        "reused_vector_source")
                reused.append({"id": ident, "embedding_input_sha256": input_hash,
                               "source_vector_sha256": vector_hash})
            else:
                require(ref["origin"] == "new_P2" and ident in PIN["new_vectors"]
                        and origin == PIN["new_vectors"][ident]
                        and origin["vector_sha256"] == vector_hash
                        and origin["input_sha256"] == input_hash, "new_vector_source")
                new.append({"id": ident, "input_sha256": input_hash})
            records.append({"id": ident, "gold_path": doc["path"], "gold_line": doc["line"],
                            "page_content_sha256": content_hash,
                            "metadata_payload_sha256": metadata_hash,
                            "embedding_input_sha256": input_hash})
            ids.append(ident)
            kinds[meta["doc_type"]] += 1
            vectors[vector_hash] += 1
            vector_ids[vector_hash].append(ident)
    require(len(ids) == len(set(ids)) == 5862, "id_coverage")
    require(sha(canonical(records)) == PIN["records_sha256"]
            and sha(canonical(ids)) == PIN["ids_sha256"], "target_fingerprints")
    require(len(reused) == 5852 and len(new) == 10
            and sha(canonical(reused)) == PIN["reuse_sha256"]
            and new == PIN["new_inputs"], "vector_partition")
    duplicates = sorted(({"vector_sha256": h, "ids": group}
                         for h, group in vector_ids.items() if len(group) > 1),
                        key=lambda x: x["vector_sha256"])
    require(duplicates == PIN["duplicate_groups"], "duplicate_groups")
    for historical in PIN["historical_duplicate_pairs"]:
        require(set(historical["ids"]) <= set(vector_ids[historical["vector_sha256"]]),
                "historical_duplicate_pair")
    stats = {"records": len(ids), "dimension": 768, "doc_types": dict(kinds),
             "reused_A": len(reused), "new_A": len(new),
             "unique_vectors": len(vectors),
             "duplicate_vector_pairs_preserved": len(PIN["historical_duplicate_pairs"]),
             "duplicate_vector_pairs_total": sum(v * (v - 1) // 2 for v in vectors.values())}
    for key, value in stats.items():
        require(manifest["content"][key] == value, "content_statistics")
    require(manifest["new_input_token_counts"] == PIN["token_counts"], "token_counts")
    return {"status": "RESPALDO_LOGICO_VERIFICADO_RECUPERACION_NO_ENSAYADA",
            "version": manifest["version"], **stats,
            "manifest_sha256": file_hash(root / "manifest.json"),
            "payload_sha256": PIN["payload_sha256"],
            "network_calls": 0, "files_changed": 0}


def main():
    try:
        require(len(sys.argv) == 1, "unexpected_arguments")
        script = Path(__file__).absolute()
        require(not script.is_symlink(), "verifier_symlink")
        result = verify_package(script.parent)
    except (ValueError, KeyError, TypeError, OSError, EOFError, OverflowError, struct.error) as exc:
        print(json.dumps({"status": "ERROR", "category": type(exc).__name__,
                          "detail": str(exc)[:120]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
