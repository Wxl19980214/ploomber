import pickle
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import matplotlib.pyplot as plt
import nbformat
import pytest

from ploomber.exceptions import DAGBuildError
from ploomber import inline


def ones(input_data):
    return pd.Series(input_data)


def twos(ones):
    return ones + 1


def both(ones, twos):
    return pd.DataFrame({"ones": ones, "twos": twos})


def multiply(first, second):
    return first * second


@inline.grid(a=[1, 2], b=[3, 4])
def add(ones, a, b):
    return ones + a + b


@inline.grid(a=[1, 2], b=[3, 4])
@inline.grid(a=[5, 6], b=[7, 8])
def add_many(ones, a, b):
    return ones + a + b


@inline.capture
def plot_ones(ones):
    # tag=plot
    plt.plot(ones)
    x = 1
    return x


@pytest.mark.parametrize('parallel', [True, False])
def test_inline(tmp_directory, parallel):
    dag = inline.dag_from_functions(
        [ones, twos, both],
        params={"ones": {
            "input_data": [1] * 3
        }},
        output='cache',
        parallel=parallel,
    )

    dag.build()

    ones_ = pickle.loads(Path('cache', 'ones').read_bytes()).to_dict()
    twos_ = pickle.loads(Path('cache', 'twos').read_bytes()).to_dict()
    both_ = pickle.loads(Path('cache', 'both').read_bytes()).to_dict()

    assert ones_ == {0: 1, 1: 1, 2: 1}
    assert twos_ == {0: 2, 1: 2, 2: 2}
    assert both_ == {'ones': {0: 1, 1: 1, 2: 1}, 'twos': {0: 2, 1: 2, 2: 2}}


def test_inline_with_manual_dependencies(tmp_directory):
    dag = inline.dag_from_functions(
        [ones, twos, multiply],
        output="cache",
        params={"ones": {
            "input_data": [1] * 3
        }},
        dependencies={"multiply": ["ones", "twos"]},
        parallel=True,
    )

    dag.build()

    ones_ = pickle.loads(Path('cache', 'ones').read_bytes()).to_dict()
    twos_ = pickle.loads(Path('cache', 'twos').read_bytes()).to_dict()
    multiply_ = pickle.loads(Path('cache', 'multiply').read_bytes()).to_dict()

    assert ones_ == {0: 1, 1: 1, 2: 1}
    assert twos_ == {0: 2, 1: 2, 2: 2}
    assert multiply_ == {0: 2, 1: 2, 2: 2}


def test_inline_grid(tmp_directory):
    dag = inline.dag_from_functions([ones, add],
                                    params={"ones": {
                                        "input_data": [1] * 3
                                    }},
                                    output='cache')

    dag.build()

    ones_ = pickle.loads(Path('cache', 'ones').read_bytes()).to_dict()
    add_0 = pickle.loads(Path('cache', 'add-0').read_bytes()).to_dict()
    add_1 = pickle.loads(Path('cache', 'add-1').read_bytes()).to_dict()
    add_2 = pickle.loads(Path('cache', 'add-2').read_bytes()).to_dict()
    add_3 = pickle.loads(Path('cache', 'add-3').read_bytes()).to_dict()

    assert ones_ == {0: 1, 1: 1, 2: 1}
    assert add_0 == {0: 5, 1: 5, 2: 5}
    assert add_1 == {0: 6, 1: 6, 2: 6}
    assert add_2 == {0: 6, 1: 6, 2: 6}
    assert add_3 == {0: 7, 1: 7, 2: 7}


def test_inline_grid_multiple(tmp_directory):
    dag = inline.dag_from_functions([ones, add_many],
                                    params={"ones": {
                                        "input_data": [1] * 3
                                    }},
                                    output='cache')

    dag.build()

    ones_ = pickle.loads(Path('cache', 'ones').read_bytes()).to_dict()

    add_many_ = [
        pickle.loads(Path('cache', f'add_many-{i}').read_bytes()).to_dict()
        for i in range(8)
    ]

    assert ones_ == {0: 1, 1: 1, 2: 1}
    assert add_many_ == [{
        0: 13,
        1: 13,
        2: 13
    }, {
        0: 14,
        1: 14,
        2: 14
    }, {
        0: 14,
        1: 14,
        2: 14
    }, {
        0: 15,
        1: 15,
        2: 15
    }, {
        0: 5,
        1: 5,
        2: 5
    }, {
        0: 6,
        1: 6,
        2: 6
    }, {
        0: 6,
        1: 6,
        2: 6
    }, {
        0: 7,
        1: 7,
        2: 7
    }]


@pytest.mark.parametrize('parallel', [True, False])
def test_capture(tmp_directory, parallel):
    dag = inline.dag_from_functions(
        [ones, plot_ones],
        params={"ones": {
            "input_data": [1] * 3
        }},
        output='cache',
        parallel=parallel,
    )

    dag.build()

    ones_ = pickle.loads(Path('cache', 'ones').read_bytes()).to_dict()
    plot_ones_ = pickle.loads(Path('cache', 'plot_ones').read_bytes())

    assert ones_ == {0: 1, 1: 1, 2: 1}
    assert plot_ones_ == 1
    assert Path('cache', 'plot_ones.html').is_file()
    nb = nbformat.reads(Path('cache', 'plot_ones.ipynb').read_text(),
                        as_version=nbformat.NO_CONVERT)
    assert nb.cells[0].metadata.tags[0] == 'plot'


# this fails since it tries to unpickle the THML
def test_capture_can_return_nothing():

    @inline.capture
    def first():
        x = 1
        return x

    # end nodes don't have to return anything
    @inline.capture
    def second(first):
        pass

    dag = inline.dag_from_functions([first, second])
    dag.build()


def test_capture_debug_now(tmp_directory, monkeypatch):

    @inline.capture
    def number():
        x, y = 1, 0
        x / y

    dag = inline.dag_from_functions([number])

    class MyException(Exception):
        pass

    mock = Mock(side_effect=MyException)
    monkeypatch.setattr(inline, 'debug_if_exception', mock)

    with pytest.raises(MyException):
        dag.build(debug='now')

    callable_ = mock.call_args[1]['callable_']
    task_name = mock.call_args[1]['task_name']

    with pytest.raises(ZeroDivisionError):
        callable_()

    assert task_name == 'number'


def test_capture_debug_later(tmp_directory, monkeypatch):

    @inline.capture
    def number():
        x, y = 1, 0
        x / y

    dag = inline.dag_from_functions([number])

    with pytest.raises(DAGBuildError):
        dag.build(debug='later')

    assert Path('number.dump').is_file()


# this fails since it tries to unpickle the HTML
def test_capture_that_depends_on_capture():

    @inline.capture
    def first():
        x = 1
        return x

    @inline.capture
    def second(first):
        return first + 1

    dag = inline.dag_from_functions([first, second])
    dag.build()


def test_root_node_with_no_arguments(tmp_directory):

    def root():
        return 1

    def add(root):
        return root + 1

    dag = inline.dag_from_functions([root, add])
    dag.build()

    root_ = pickle.loads(Path('output', 'root').read_bytes())
    add_ = pickle.loads(Path('output', 'add').read_bytes())

    assert root_ == 1
    assert add_ == 2


# TODO: also test with grid
def test_decorated_root_with_input_data():

    # this is failing because it's not passing input_data - we're not
    # validating the signature,and just modifying the user's namespace,
    # but we have to, otherwise the error is confusing: "input_data" is not
    # defined
    @inline.capture
    def root(input_data):
        x = input_data + 1
        return x

    dag = inline.dag_from_functions([root])
    dag.build()


# TODO: also try with grid
# NOTE: this is failing because it's trying to unpickle the html
def test_decorated_root_without_arguments(tmp_directory):

    @inline.capture
    def root():
        x = 1
        return x

    def add(root):
        return root + 1

    dag = inline.dag_from_functions([root, add])
    dag.build()

    root_ = pickle.loads(Path('output', 'root').read_bytes())
    add_ = pickle.loads(Path('output', 'add').read_bytes())

    assert root_ == 1
    assert add_ == 2


def get():
    df = pd.DataFrame({'target': [1, 0, 0, 1], 'a': [1, 2, 3, 4]})
    return df


@inline.capture
@inline.grid(model=[
    'RandomForestClassifier',
    'AdaBoostClassifier',
    'ExtraTreesClassifier',
])
def fit(get, model):
    _ = get.drop('target', axis='columns')
    _ = get.target

    # tag=plot
    plt.plot([1, 2, 3])

    return model


def test_decorated_with_capture_and_grid(tmp_directory):
    dag = inline.dag_from_functions([get, fit])
    dag.build()

    nb = nbformat.reads(Path('output', 'fit-0.ipynb').read_text(),
                        as_version=nbformat.NO_CONVERT)
    assert nb.cells[-2].metadata.tags[0] == 'plot'


def fn():
    x, y = (  # noqa
        1,
        2,
    )

    i, j = (  # noqa
        1,
        2,
    )


def test_get_body_statements():
    assert len(inline.get_body_statements(fn)) == 2


def test_deindents_statements():
    # we're currently passing statements to IPython with the indentation, this
    # breaks when using parso.parse to
    # extract the return statement - the current: cell.source.strip()
    # only works on simple cases
    raise NotImplementedError


@pytest.mark.parametrize('source, expected', [
    ['# tag=plot', 'plot'],
    ['# tag=cool_plot', 'cool_plot'],
    ['# tag=cool-plot', 'cool-plot'],
    ['# tag=plot0', 'plot0'],
    ['# tag=0plot', '0plot'],
    ['\n    # tag=plot\n    plot.confusion_matrix(y_test, y_pred)\n', 'plot'],
])
def test_parse_tag(source, expected):
    assert inline.parse_tag(source) == expected


def test_aborted_when_task_fails():
    raise NotImplementedError