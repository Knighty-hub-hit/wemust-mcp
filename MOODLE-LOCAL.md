# Moodle read-only tools

This checkout adds four read-only tools to the original project:

- `get_moodle_courses`: enrolled courses, with IDs and names.
- `get_moodle_course(course_id)`: visible course-page text and activity/resource links.
- `get_moodle_assignment(course_id, activity_id)`: teacher instructions from the assignment
  detail page, including attachment/image links (not their file contents). Activity ID is
  the course-module ID in `/mod/assign/view.php?id=...`. Submission and grade panels are omitted.
- `get_moodle_deadlines(days=30)`: upcoming Moodle action-calendar entries (Macau time).

Authentication reuses the existing CAS login and the same user's in-memory cookies.
Only two read-only Moodle AJAX methods are allowed. Course pages are restricted
to enrolled course IDs. No submission, completion marking, file upload, or grade
API is implemented. Resource links are returned; file contents are not downloaded.
Calendar results are not a complete inventory of assignments: teachers must create
visible calendar events. Results are capped at 30 events and report truncation.
Course-page text is capped at 40,000 characters. The course page is untrusted input.

On Windows, the optional scripts in `windows/` store a DPAPI-encrypted credential
in `.local/credential.xml`. Never commit that file. macOS and other clients can
continue using the original Keychain/environment configuration. Restart the MCP
client after modifying the server to reload its tool list.

Offline verification: `python -m unittest discover -s tests`.
