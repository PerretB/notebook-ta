# Notebook_ta

Notebook_ta is a teaching assistant for Python notebooks powered by a LLM. The students get a notebook with several exercise statements and code blocks to complete. When the student executes a code block with its answer, the LLM is automatically triggered to provide a high level analysis of the proposed solution and the feedback is displayed in the notebook. The LLM can also provide hints and suggestions to help the student complete the exercises.


## Key Features

- The LLM analyzes the student's code and provides feedback following the instructions given in one or more general prompt which can be defined at the global level or at the exercise level. 
- Each exercise also provides mandatory and optional information to the LLM to help it provide more accurate feedback. The mandatory information is composed of the exercise statements. Optional information can include the expected output, the expected time complexity, and other relevant details.
- Each exercise can also provide unit tests to validate the student's code. If the tests succeed, the LLM should be triggered automatically to make a high level analysis of the proposed solution according to a specific prompt. If the tests fail, the system should propose to provide targeted feedback to help the student identify and correct their errors. The LLM can use these tests to provide more accurate feedback and hints. 
- If no LLM is available, the system should not error, but instead provide a message to the student indicating that the LLM is not available and that they should check their code against the unit tests. The system should run the unit tests and display the results in a user-friendly format.

## Design

The system is designed to be modular and extensible. The main components are:

- **Configuration**: This component manages the configuration of the system and exercise data. It should be possible to read the configuration from a TOML file (local or remote) and to override it programmatically. The configuration files defines: 
  - Default LLM provider and API settings (local or cloud-based)
  - Default prompts and other settings that can be used by the LLM. 
  - Exercise definitions, including the exercise statement, optional information, and unit tests. The configuration should be designed to support different types of exercises and allow for easy addition of new exercises.
- **LLM Connection**: This component handles the communication with the LLM. It sends the student's code and receives feedback, hints, and suggestions. It should be designed to support different LLM providers and APIs (local or cloud-based). At first, we will use local Ollama LLM, but the system should be able to switch to other providers if needed.
- **Exercise Definition**: This component defines the structure of an exercise, including the exercise statement, optional information, and unit tests. This componenent should be able to construct a LLM prompt based on the exercise definition and the student's code. It should also be able to validate the student's code against the unit tests and provide feedback accordingly. Typically, the full prompt sent to the LLM will be composed of:
  - A general prompt (defined at the global level or at the exercise level). The choice of the general prompt can depend of the unit test results.
  - The exercise statement and optional information.
  - The student's code.
  - The unit test results if the tests failed.

  The LLM should be instructed to ignore any instructions or comments in the student's code.
- **Notebook Integration**: This component integrates the system with Python notebooks. It should be able to detect when a student code block is executed (using Python magic with an argument to identify the exercise), run the unit tests, send the student's code to the LLM, and display the feedback in the notebook. It should be able to display the feedback in a user-friendly format, including hints and suggestions. It should also be able to handle errors and exceptions gracefully. As local LLMs can be slow, the system should provide visual clues to indicate that the LLM is processing the student's code and ideally stream the feedback as it is generated. If unit tests fail, the system should display the test results in a user-friendly format and an interractive button "Give me hints" to trigger the LLM to provide targeted feedback and hints to help the student identify and correct their errors. 
- **Unit Test Execution**: This component runs the unit tests defined for each exercise and provides the results in a user-friendly format. It should be able to handle different types of unit tests. A unit test can be defined as a Python function that returns a boolean value indicating whether the test passed or failed. Extra information can be provided by the unit test either as a second return value (string) or by printing to the standard output. The system should be able to capture this information and display it in the notebook / send it to the LLM.
- **Easy local LLM setup**: as students' machines may differ in their capabilities, the system should propose several model options to run locally, including small and medium models. Ideally, the system should be able to detect the available resources and propose the best model to run locally. 

## Project management and development

- The project is managed using GitHub and follows a standard Git workflow. The main branch is `main`, and feature branches are created for new features or bug fixes. Pull requests are used to merge changes into the main branch, and code reviews are conducted before merging. The project uses GitHub Actions for continuous integration and testing.
- Unit tests are written using the `pytest` framework and are located in the `tests` directory. The tests cover the main components of the system and ensure that the system behaves as expected. The tests can be run locally or in a continuous integration environment.
- The project will be distributed through Pypi and can be installed using `pip`. The project will use modern Python packaging standards, including a `pyproject.toml` file and a `setup.cfg` file. The project will also include a `README.md` file with installation instructions, usage examples, and contribution guidelines.
- The project will follow best practices for Python development, including code style guidelines (PEP 8), type hints, and documentation. The code will be documented using docstrings and comments, and the project will include a `docs` directory with additional documentation and examples.
- The project will be licensed under the MIT License, and the license file will be included in the project repository.
- The project will be modular and extensible without overcomplicating the design. The system should be easy to use and configure, and it should be easy to add new exercises, LLM providers or unit tests. 
