"""The public body class is an optional factual value with explicit provenance."""

from fastapi import FastAPI
import pytest

from edfinder_api.routers import v3


pytestmark = pytest.mark.unit


def test_body_openapi_exposes_nullable_class_and_known_source():
    app = FastAPI()
    app.include_router(v3.router)
    spec = app.openapi()
    schema = spec['components']['schemas']['BodyV1']
    properties = schema['properties']
    assert properties['body_class']['anyOf'] == [{'type': 'string'}, {'type': 'null'}]
    assert properties['body_class_source']['anyOf'] == [
        {'type': 'string', 'const': 'ratings-v4-derived'}, {'type': 'null'},
    ]
    assert not {'body_class', 'body_class_source'} & set(schema['required'])
    operation = spec['paths']['/api/v1/systems/{system_id}/bodies']['get']
    assert operation['operationId'] == 'listV3SystemBodies'
    assert operation['responses']['200']['content']['application/json']['schema']['items'] == {
        '$ref': '#/components/schemas/BodyV1',
    }
