# Setup

Use Python 3.9 or newer and install the dependencies required for the handoff:

```bash
python -m pip install -r requirements.txt
```

`ifcopenshell` is required to create or inspect IFC. `pandas` is required for
the client-format CSV processor. Blender and Bonsai are optional authoring
tools for a terrain IFC; they are not run by the CSV-to-IFC command.

Run the supported workflow with an input file and a safe output location:

```bash
python experiments/prototypes/complete_client_workflow.py path/to/survey.csv \
  --output-dir /safe/output/survey-run
```

If no output location is supplied, the command creates a new temporary
directory. It will not write to the repository's tracked sample output
directories or overwrite a prior output.

To export LandXML, author and review a terrain TIN in IFC first, then use the
terrain command documented in [the workflow](WORKFLOW.md). The repository does
not claim validation by any field machine or third-party application.
