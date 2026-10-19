import argparse
import os
import shutil
import sqlite3
from datetime import datetime

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))
DEFAULT_DB = os.getenv('DATABASE_FILE', os.path.join(BASE_DIR, 'library.db'))

TABLES = {
    'Login': "name TEXT, userid TEXT, password INTEGER, branch TEXT, mobile INTEGER",
    'Book': "subject TEXT, title TEXT, author TEXT, serial INTEGER PRIMARY KEY",
    'BookIssue': "stdid TEXT, serial TEXT, issue DATE, exp DATE",
    'BookReturn': "stdid TEXT, title TEXT, copies INTEGER, issue DATE, returned DATE",
    'BookReturnDetail': "stdid TEXT, title TEXT, book_id TEXT, issue DATE, returned DATE",
    'DeletedLogin': "name TEXT, userid TEXT, deleted DATE",
    'DeletedBook': "subject TEXT, title TEXT, author TEXT, book_id TEXT, deleted DATE",
}

COLUMNS = [
    ('Book', 'book_id', "TEXT", [
        "UPDATE Book SET book_id = CAST(serial AS TEXT) WHERE book_id IS NULL OR book_id = ''",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_book_book_id ON Book(book_id)",
    ]),
    ('BookIssue', 'book_id', "TEXT", [
        "UPDATE BookIssue SET book_id = (SELECT b.book_id FROM Book b WHERE CAST(b.serial AS TEXT) = BookIssue.serial) "
        "WHERE book_id IS NULL",
    ]),
    ('BookIssue', 'assigned_by', "TEXT", []),
    ('Login', 'email', "TEXT", []),
    ('BookReturnDetail', 'returned_by', "TEXT", []),
    ('Login', 'borrower_group', "TEXT", []),
    ('Login', 'role', "TEXT DEFAULT 'borrower'", []),
    ('Book', 'dewey', "TEXT", []),
    ('DeletedBook', 'dewey', "TEXT", []),
]


def existing_tables(cur):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0].lower() for row in cur.fetchall()}


def existing_columns(cur, table):
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1].lower() for row in cur.fetchall()}


def pending_changes(cur):
    tables = existing_tables(cur)
    new_tables = [name for name in TABLES if name.lower() not in tables]
    new_columns = []
    for table, column, definition, backfill in COLUMNS:
        have = set() if table in new_tables else existing_columns(cur, table)
        if column.lower() not in have:
            new_columns.append((table, column, definition, backfill))
    return new_tables, new_columns


def main():
    parser = argparse.ArgumentParser(description='Create or update the library database schema.')
    parser.add_argument('--db', default=DEFAULT_DB, help='SQLite database file (default: %(default)s)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without changing anything')
    args = parser.parse_args()

    is_new = not os.path.exists(args.db)
    if is_new and args.dry_run:
        print(f'{args.db} does not exist yet; it would be created with all tables.')
        return
    if is_new:
        os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    new_tables, new_columns = pending_changes(cur)

    for name in new_tables:
        print(f'Table {name}: will be created')
    for table, column, definition, backfill in new_columns:
        extra = f' + {len(backfill)} backfill step(s)' if backfill else ''
        print(f'{table}.{column}: will be added ({definition}){extra}')

    if not (new_tables or new_columns):
        print('Database is up to date.')
    elif args.dry_run:
        print(f'Dry run: {len(new_tables)} table(s) and {len(new_columns)} column(s) would change. Nothing changed.')
    else:
        if not is_new:
            backup = os.path.join(os.path.dirname(os.path.abspath(args.db)),
                                  f"library_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            shutil.copy2(args.db, backup)
            print(f'Backup saved: {backup}')
        with conn:
            for name in new_tables:
                cur.execute(f"CREATE TABLE IF NOT EXISTS {name}({TABLES[name]})")
            for table, column, definition, backfill in new_columns:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                for statement in backfill:
                    cur.execute(statement)
        print(f'Done: created {len(new_tables)} table(s), added {len(new_columns)} column(s).')
    conn.close()


if __name__ == '__main__':
    main()
