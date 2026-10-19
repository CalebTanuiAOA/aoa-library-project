# AOA Library

Library management app for the AOA library, written in Flask with a SQLite database.

The database has the full book catalogue (about 1,500 copies), two demo users and no loans.

## Running it

```bash
pip install -r requirements.txt
python migrate_db.py
python app.py
```

Open http://localhost:5001.

## Views

There is no login. Use the "View as" menu at the top to switch between:

- Admin: catalogue, borrowers, loans, returns and history
- Staff: browse the library, assign and return books, see their own books
- Borrower: browse the library and see their own books

Demo users:

- Demo Staff (staff, Faculty) - staff@example.com
- Demo Borrower (borrower, Y1) - borrower@example.com

New people can be added on the Borrowers page. Set the role to Staff to make someone staff.

## Files

- `app.py` - Flask server and the JSON API under `/api/`
- `migrate_db.py` - creates and updates the database tables
- `templates/app.html`, `static/app/app.js`, `static/app/styles.css` - the frontend
- `classify_dewey.py` - script that set the Dewey numbers of the books
- `library.db` - the database

## Database tables

- `Book` - one row per copy: `subject` (category), `title`, `author`, `book_id`, `dewey`
- `Login` - borrowers: `userid`, `name`, `email`, `borrower_group`, `role`
- `BookIssue` - books on loan
- `BookReturn`, `BookReturnDetail` - returned books
- `DeletedBook`, `DeletedLogin` - deleted books and borrowers

To add a table or column, add it to `TABLES` or `COLUMNS` in `migrate_db.py` and run
`python migrate_db.py` (use `--dry-run` to preview).

## Email

Loan, return and reminder emails are sent with Resend when `RESEND_API_KEY` is set.
Without it, no emails are sent. See `.env.example`.
