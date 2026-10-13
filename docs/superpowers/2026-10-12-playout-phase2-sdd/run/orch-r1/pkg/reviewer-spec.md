# Your seat: SPEC COMPLIANCE
Compare the diff against the brief (and the constraints file's rulings it touches):
- Missing: requirements skipped, or claimed without being implemented (every test the brief names must exist
  with the brief's name and assert what the brief says).
- Extra: features not requested, over-engineering.
- Misunderstood: right feature built the wrong way; exact values (constants, keys, formats, signatures) differ
  from the brief.
- Every file the brief lists must be touched as stated; a listed file the diff never touches is Missing.
Code quality is a separate reviewer's seat; mention a quality issue only if it makes behaviour wrong.
