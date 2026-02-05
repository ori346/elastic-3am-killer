# ToolResult System Unit Tests

Comprehensive unit test suite for the OpenShift Alert Remediation ToolResult system. These tests verify the structured data models, error handling, and tool functionality without requiring actual OpenShift cluster access.

## Test Structure

```
tests/
├── README.md                     # This file
├── unit/                         # Unit test modules and configuration
│   ├── conftest.py              # Shared pytest fixtures and configuration
│   ├── requirements-test.txt    # Testing dependencies for unit tests
│   ├── run_unit_tests.py        # Test runner script for unit tests
│   ├── test_models.py           # ToolResult and error model validation tests
│   ├── test_error_handling.py   # Error classification and handling tests
│   ├── test_utils.py            # Utility function tests (parsing, formatting)
│   ├── test_pod_tools.py        # Pod tool tests (mocked oc commands)
│   ├── test_deployment_tools.py # Deployment tool tests (mocked oc commands)
│   └── test_context_tools.py    # Context tool tests (mocked LlamaIndex Context)
├── common/                      # Common test infrastructure
│   └── setup.py                 # Test environment setup
└── [other test suites...]       # Integration and other test directories
```

## What is Tested

### 1. **Pydantic Models** (`test_models.py`)
- ToolResult, ToolError, and all structured data models
- Field validation, defaults, and computed properties
- Model serialization and data access patterns

### 2. **Error Handling** (`test_error_handling.py`)
- Error type classification from oc command output
- Error suggestion generation based on context
- ToolResult error creation and recovery patterns

### 3. **Utility Functions** (`test_utils.py`)
- oc command execution utilities
- Pod name finding and partial matching
- Text parsing and formatting functions

### 4. **Pod Tools** (`test_pod_tools.py`)
- `oc_get_pods`, `oc_describe_pod`, `oc_describe_pod`
- `oc_get_events`, `oc_get_logs`
- Structured data conversion from JSON to Pydantic models
- Error handling for various failure scenarios

### 5. **Deployment Tools** (`test_deployment_tools.py`)
- `oc_get_deployments`, `oc_get_deployment_resources`
- `oc_describe_deployment`
- Deployment condition analysis and structured field access

### 6. **Context Tools** (`test_context_tools.py`)
- `read_alert_diagnostics_data`, `write_remediation_plan`
- Context store operations and validation
- Read-only command filtering and plan validation

## Key Features

### ✅ **No External Dependencies**
- All `oc` commands are mocked using `unittest.mock`
- LlamaIndex Context operations are mocked
- No actual OpenShift cluster access required
- Tests run in isolation and are deterministic

### ✅ **Comprehensive Coverage**
- Success and failure paths for all tools
- Error classification and recovery scenarios
- Structured data access patterns used by agents
- Integration between different components

### ✅ **Agent Workflow Validation**
- Tests verify structured field access: `pod.status`, `deployment.ready_replicas`
- Tests validate error handling patterns agents expect
- Tests confirm ToolResult interface consistency

### ✅ **Real-world Scenarios**
- Partial pod name matching (e.g., "frontend" → "frontend-698f45c955-hbkjz")
- Command timeout and network error handling
- Invalid JSON parsing and malformed responses
- Permission and authentication errors

## Running Tests

### Quick Start
```bash
# Install testing dependencies
pip install -r tests/unit/requirements-test.txt

# Run all tests
python tests/unit/run_unit_tests.py

# Run specific test module
python tests/unit/run_unit_tests.py -m test_pod_tools

# Run with verbose output
python tests/unit/run_unit_tests.py -v
```

### Using pytest directly
```bash
# Run all unit tests
pytest unit/ -v

# Run specific test file
pytest unit/test_models.py -v

# Run with coverage
pytest unit/ --cov=app.agents.remediation
```

### List available test modules
```bash
python tests/unit/run_unit_tests.py --list-modules
```

## Test Fixtures

The `conftest.py` file provides comprehensive fixtures for testing:

- **Sample Data**: Pod JSON, deployment JSON, events JSON
- **Model Fixtures**: Pre-built Pydantic model instances
- **Mock Fixtures**: Mocked subprocess and context operations
- **Parametrized Tests**: Error classification and name matching scenarios

## Example Test Patterns

### Testing ToolResult Success Path
```python
@patch('app.agents.remediation.pod_tools.run_oc_command')
def test_get_pods_success(self, mock_run_oc, sample_pods_list_json):
    mock_run_oc.return_value = (0, json.dumps(sample_pods_list_json), "")

    result = oc_get_pods("test-namespace")

    assert result.success is True
    assert isinstance(result.data, list)
    assert len(result.data) == 2
    assert result.data[0].name == "frontend-698f45c955-hbkjz"
```

### Testing ToolResult Error Path
```python
@patch('app.agents.remediation.pod_tools.run_oc_command')
def test_get_pods_not_found(self, mock_run_oc):
    mock_run_oc.return_value = (1, "", "namespace not found")

    result = oc_get_pods("missing-namespace")

    assert result.success is False
    assert result.error.type == ErrorType.NOT_FOUND
    assert "missing-namespace" in result.error.message
```

### Testing Async Context Tools
```python
@pytest.mark.asyncio
async def test_read_alert_data_success(self, mock_context):
    mock_context.store.get = AsyncMock(return_value={
        "namespace": "production",
        "alert_name": "PodCrashLoopBackOff"
    })

    result = await read_alert_diagnostics_data(mock_context)
    assert result.success is True
    assert result.data["namespace"] == "production"
```

## Benefits

### 🚀 **Fast Feedback**
- Tests run in seconds without cluster dependencies
- Early detection of model validation issues
- Quick verification of agent integration patterns

### 🛡️ **Error Prevention**
- Validates error classification accuracy
- Tests recovery scenarios and suggestions
- Ensures structured data consistency

### 📋 **Documentation**
- Tests serve as usage examples for each tool
- Demonstrates expected error handling patterns
- Shows structured data access patterns

### 🔄 **CI/CD Ready**
- No external dependencies or credentials required
- Deterministic test results
- Suitable for automated testing pipelines

## Integration with Existing Tests

This unit test suite complements the existing integration tests:

- **Unit tests** (this suite): Fast, isolated, comprehensive coverage
- **Integration tests** (`queue-depth-test/`, `service-dependency-test/`): End-to-end workflows with real containers

Together, they provide complete test coverage from individual function validation to full agent orchestration scenarios.

## Future Enhancements

1. **Property-based testing**: Use `hypothesis` for fuzzing model validation
2. **Performance benchmarks**: Measure ToolResult overhead vs plain returns
3. **Contract testing**: Verify agent expectations match tool outputs
4. **Mutation testing**: Ensure test quality with `mutmut`