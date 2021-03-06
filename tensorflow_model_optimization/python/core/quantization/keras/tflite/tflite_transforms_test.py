# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for TFLite Transforms."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from absl.testing import parameterized

import numpy as np
import tensorflow as tf

from tensorflow_model_optimization.python.core.quantization.keras import quantize
from tensorflow_model_optimization.python.core.quantization.keras import quantize_aware_activation
from tensorflow_model_optimization.python.core.quantization.keras import quantize_layer
from tensorflow_model_optimization.python.core.quantization.keras import quantizers
from tensorflow_model_optimization.python.core.quantization.keras.graph_transformations import model_transformer
from tensorflow_model_optimization.python.core.quantization.keras.layers import conv_batchnorm_test_utils
from tensorflow_model_optimization.python.core.quantization.keras.tflite import tflite_quantize_configs
from tensorflow_model_optimization.python.core.quantization.keras.tflite import tflite_transforms

ModelTransformer = model_transformer.ModelTransformer

Conv2DModel = conv_batchnorm_test_utils.Conv2DModel
DepthwiseConv2DModel = conv_batchnorm_test_utils.DepthwiseConv2DModel

keras = tf.keras

Conv2DBatchNormActivationQuantize = tflite_transforms.Conv2DBatchNormActivationQuantize
Conv2DBatchNormReLUQuantize = tflite_transforms.Conv2DBatchNormReLUQuantize


# TODO(alanchiao): reduce redundancy by parameterizing on Depthwise vs Conv.
class TFLiteTransformsTest(tf.test.TestCase, parameterized.TestCase):

  def testTransformsConvBNReLUPattern(self):
    model = Conv2DModel.get_nonfolded_batchnorm_model(
        post_bn_activation=keras.layers.ReLU(6.0), model_type='functional')
    folded_model = Conv2DModel.get_folded_batchnorm_model(
        post_bn_activation=keras.layers.ReLU(6.0), is_quantized=True)

    transformed_model, _ = ModelTransformer(
        model, [tflite_transforms.Conv2DBatchNormReLU6Fold()]).transform()

    inputs = np.random.standard_normal(Conv2DModel.get_batched_input_shape())
    self.assertAllClose(
        transformed_model.predict(inputs), folded_model.predict(inputs))

  def testTransformsConvBNReLUPatternPreservesWeights(self):
    # random_init to prevent non-random initialization in resulting
    # in same weights between transformed and non-transformed models.
    model = Conv2DModel.get_nonfolded_batchnorm_model(
        post_bn_activation=keras.layers.ReLU(6.0),
        model_type='functional',
        random_init=True)

    transformed_model, _ = ModelTransformer(
        model, [tflite_transforms.Conv2DBatchNormReLU6Fold()]).transform()

    transformed_weights = transformed_model.get_weights()
    # Remove quantization related weights.
    del transformed_weights[3:8]

    self.assertEqual(len(transformed_weights), len(model.get_weights()))
    for i in range(len(transformed_weights)):
      self.assertAllEqual(transformed_weights[i], model.get_weights()[i])

  def testTransformsConvBNPattern(self):
    model = Conv2DModel.get_nonfolded_batchnorm_model(
        model_type='functional')
    folded_model = Conv2DModel.get_folded_batchnorm_model(
        is_quantized=True)

    with quantize.quantize_scope():
      transformed_model, _ = ModelTransformer(
          model, [tflite_transforms.Conv2DBatchNormFold()]).transform()

    inputs = np.random.standard_normal(Conv2DModel.get_batched_input_shape())
    self.assertAllClose(
        transformed_model.predict(inputs), folded_model.predict(inputs))

  def testTransformsConvBNPatternPreservesWeights(self):
    # random_init to prevent non-random initialization in resulting
    # in same weights between transformed and non-transformed models.
    model = Conv2DModel.get_nonfolded_batchnorm_model(
        model_type='functional',
        random_init=True)

    transformed_model, _ = ModelTransformer(
        model,
        [tflite_transforms.Conv2DBatchNormFold()]).transform()

    transformed_weights = transformed_model.get_weights()
    # Remove quantization related weights.
    del transformed_weights[3:8]

    self.assertEqual(len(transformed_weights), len(model.get_weights()))
    for i in range(len(transformed_weights)):
      self.assertAllEqual(transformed_weights[i], model.get_weights()[i])

  def testTransformsDepthwiseConvBNReLUPattern(self):
    model = DepthwiseConv2DModel.get_nonfolded_batchnorm_model(
        post_bn_activation=keras.layers.ReLU(6.0), model_type='functional')
    folded_model = DepthwiseConv2DModel.get_folded_batchnorm_model(
        post_bn_activation=keras.layers.ReLU(6.0), is_quantized=True)

    transformed_model, _ = ModelTransformer(
        model,
        [tflite_transforms.DepthwiseConv2DBatchNormReLU6Fold()]).transform()

    inputs = np.random.standard_normal(
        DepthwiseConv2DModel.get_batched_input_shape())
    self.assertAllClose(
        transformed_model.predict(inputs), folded_model.predict(inputs))

  def testTransformsDepthwiseConvBNReLUPatternPreservesWeights(self):
    # random_init to prevent non-random initialization in resulting
    # in same weights between transformed and non-transformed models.
    model = DepthwiseConv2DModel.get_nonfolded_batchnorm_model(
        post_bn_activation=keras.layers.ReLU(6.0),
        model_type='functional',
        random_init=True)

    transformed_model, _ = ModelTransformer(
        model,
        [tflite_transforms.DepthwiseConv2DBatchNormReLU6Fold()]).transform()

    transformed_weights = transformed_model.get_weights()
    # Remove quantization related weights.
    del transformed_weights[3:8]

    self.assertEqual(len(transformed_weights), len(model.get_weights()))
    for i in range(len(transformed_weights)):
      self.assertAllEqual(transformed_weights[i], model.get_weights()[i])

  @staticmethod
  def _get_model(layer_type, activation_type):
    activation = None
    if activation_type == 'relu':
      activation = keras.layers.ReLU(6.0)
    elif activation_type == 'act_relu':
      activation = keras.layers.Activation('relu')

    if layer_type == 'Conv2D':
      return Conv2DModel.get_nonfolded_batchnorm_model(
          model_type='functional', post_bn_activation=activation)
    elif layer_type == 'DepthwiseConv2D':
      return DepthwiseConv2DModel.get_nonfolded_batchnorm_model(
          model_type='functional', post_bn_activation=activation)

  @staticmethod
  def _get_input_shape(layer_type):
    if layer_type == 'Conv2D':
      return Conv2DModel.get_batched_input_shape()
    elif layer_type == 'DepthwiseConv2D':
      return DepthwiseConv2DModel.get_batched_input_shape()

  @parameterized.parameters('Conv2D', 'DepthwiseConv2D')
  def testConv2DBatchNormQuantize(self, layer_type):
    model = self._get_model(layer_type, False)
    input_shape = self._get_input_shape(layer_type)

    transformed_model, updated_metadata = ModelTransformer(
        model,
        [tflite_transforms.Conv2DBatchNormQuantize()],
    ).transform()

    conv_layer = transformed_model.layers[1]
    bn_layer = transformed_model.layers[2]

    self.assertIsInstance(
        conv_layer.activation, quantize_aware_activation.NoOpActivation)
    self.assertIsInstance(
        updated_metadata.get(bn_layer.name).get('quantize_config'),
        tflite_quantize_configs.OutputQuantizeConfig)

    inputs = np.random.standard_normal(input_shape)
    self.assertAllClose(
        transformed_model.predict(inputs), model.predict(inputs))

  @parameterized.parameters(
      ('Conv2D', 'relu', Conv2DBatchNormReLUQuantize),
      ('Conv2D', 'act_relu', Conv2DBatchNormActivationQuantize),
      ('DepthwiseConv2D', 'relu', Conv2DBatchNormReLUQuantize),
      ('DepthwiseConv2D', 'act_relu', Conv2DBatchNormActivationQuantize),
  )
  def testConv2DBatchNormReLUQuantize(
      self, layer_type, activation_type, transform_type):
    model = self._get_model(layer_type, activation_type)
    input_shape = self._get_input_shape(layer_type)

    transformed_model, updated_metadata = ModelTransformer(
        model,
        [transform_type()],
    ).transform()

    conv_layer = transformed_model.layers[1]
    bn_layer = transformed_model.layers[2]

    self.assertIsInstance(
        conv_layer.activation, quantize_aware_activation.NoOpActivation)
    self.assertIsInstance(
        updated_metadata.get(bn_layer.name).get('quantize_config'),
        tflite_quantize_configs.NoOpQuantizeConfig)

    inputs = np.random.standard_normal(input_shape)
    self.assertAllClose(
        transformed_model.predict(inputs), model.predict(inputs))

  def testAddsQuantizeLayerAfterInputLayer(self):
    inp1 = keras.layers.Input((3,))
    inp2 = keras.layers.Input((3,))
    x = keras.layers.Concatenate()([inp1, inp2])
    model = keras.Model([inp1, inp2], x)

    transformed_model, _ = ModelTransformer(
        model, [tflite_transforms.InputLayerQuantize()]).transform()

    for input_layer in transformed_model._input_layers:
      layer_after_input = input_layer._outbound_nodes[0].outbound_layer
      self.assertIsInstance(
          layer_after_input,
          quantize_layer.QuantizeLayer)
      self.assertIsInstance(
          layer_after_input.quantizer, quantizers.MovingAverageQuantizer)


if __name__ == '__main__':
  tf.test.main()
