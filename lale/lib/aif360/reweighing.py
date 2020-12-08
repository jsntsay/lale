# Copyright 2020 IBM Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import aif360.algorithms.preprocessing
import numpy as np

import lale.docstrings
import lale.operators

from .protected_attributes_encoder import ProtectedAttributesEncoder
from .util import (
    _categorical_fairness_properties,
    _group_flag,
    _ndarray_to_series,
    _PandasToDatasetConverter,
)


class ReweighingImpl:
    def __init__(
        self, estimator, favorable_labels, protected_attributes,
    ):
        self.estimator = estimator
        self.favorable_labels = favorable_labels
        self.protected_attributes = protected_attributes

    def fit(self, X, y):
        prot_attr_enc = ProtectedAttributesEncoder(
            protected_attributes=self.protected_attributes
        )
        encoded_X = prot_attr_enc.transform(X)
        if isinstance(y, np.ndarray):
            encoded_y = _ndarray_to_series(y, X.shape[1])
        else:
            encoded_y = y
        encoded_y = encoded_y.apply(lambda v: _group_flag(v, self.favorable_labels))
        pans = [pa["feature"] for pa in self.protected_attributes]
        pandas_to_dataset = _PandasToDatasetConverter(
            favorable_label=1, unfavorable_label=0, protected_attribute_names=pans
        )
        encoded_data = pandas_to_dataset(encoded_X, encoded_y)
        unpriv_groups = [{pa["feature"]: 0 for pa in self.protected_attributes}]
        priv_groups = [{pa["feature"]: 1 for pa in self.protected_attributes}]
        reweighing_trainable = aif360.algorithms.preprocessing.Reweighing(
            unprivileged_groups=unpriv_groups, privileged_groups=priv_groups,
        )
        reweighing_trained = reweighing_trainable.fit(encoded_data)
        reweighted_data = reweighing_trained.transform(encoded_data)
        sample_weight = reweighted_data.instance_weights
        if isinstance(self.estimator, lale.operators.TrainablePipeline):
            trainable_prefix = self.estimator.remove_last()
            trainable_suffix = self.estimator.get_last()
            trained_prefix = trainable_prefix.fit(X, y)
            transformed_X = trained_prefix.transform(X)
            trained_suffix = trainable_suffix.fit(
                transformed_X, y, sample_weight=sample_weight
            )
            self.estimator = trained_prefix >> trained_suffix
        else:
            self.estimator = self.estimator.fit(X, y, sample_weight=sample_weight)
        return self

    def predict(self, X):
        result = self.estimator.predict(X)
        return result


_input_fit_schema = {
    "description": "Input data schema for training.",
    "type": "object",
    "required": ["X", "y"],
    "additionalProperties": False,
    "properties": {
        "X": {
            "description": "Features; the outer array is over samples.",
            "type": "array",
            "items": {
                "type": "array",
                "items": {"anyOf": [{"type": "number"}, {"type": "string"}],},
            },
        },
        "y": {
            "description": "The predicted classes.",
            "anyOf": [
                {"type": "array", "items": {"type": "number"}},
                {"type": "array", "items": {"type": "string"}},
                {"type": "array", "items": {"type": "boolean"}},
            ],
        },
    },
}

_input_predict_schema = {
    "description": "Input data schema for transform.",
    "type": "object",
    "required": ["X"],
    "additionalProperties": False,
    "properties": {
        "X": {
            "description": "Features; the outer array is over samples.",
            "type": "array",
            "items": {
                "type": "array",
                "items": {"anyOf": [{"type": "number"}, {"type": "string"}],},
            },
        },
    },
}

_output_predict_schema = {
    "description": "The predicted classes.",
    "anyOf": [
        {"type": "array", "items": {"type": "number"}},
        {"type": "array", "items": {"type": "string"}},
        {"type": "array", "items": {"type": "boolean"}},
    ],
}

_hyperparams_schema = {
    "description": "Hyperparameter schema.",
    "allOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["estimator", "favorable_labels", "protected_attributes"],
            "relevantToOptimizer": [],
            "properties": {
                "estimator": {
                    "description": "Nested classifier, fit method must support sample_weight.",
                    "laleType": "operator",
                },
                "favorable_labels": _categorical_fairness_properties[
                    "favorable_labels"
                ],
                "protected_attributes": _categorical_fairness_properties[
                    "protected_attributes"
                ],
            },
        }
    ],
}

_combined_schemas = {
    "description": """`Reweighing`_ preprocessor for fairness mitigation.

.. _`Reweighing`: https://aif360.readthedocs.io/en/latest/modules/generated/aif360.sklearn.preprocessing.Reweighing.html
""",
    "documentation_url": "https://lale.readthedocs.io/en/latest/modules/lale.lib.aif360.reweighing.html",
    "import_from": "aif360.sklearn.preprocessing",
    "type": "object",
    "tags": {"pre": [], "op": ["estimator", "classifier"], "post": []},
    "properties": {
        "hyperparams": _hyperparams_schema,
        "input_fit": _input_fit_schema,
        "input_predict": _input_predict_schema,
        "output_predict": _output_predict_schema,
    },
}

lale.docstrings.set_docstrings(ReweighingImpl, _combined_schemas)

Reweighing = lale.operators.make_operator(ReweighingImpl, _combined_schemas)
