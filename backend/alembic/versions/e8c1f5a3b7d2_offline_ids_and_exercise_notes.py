"""offline client ids and exercise notes

Revision ID: e8c1f5a3b7d2
Revises: d2b7e4a9c1f3
Create Date: 2026-10-07

Solo aggiunte, nessun dato toccato:
- `client_id` (nullable) su sessioni e serie: l'identificativo che il
  telefono dà a ciò che salva senza rete, così un invio ripetuto non crea
  doppioni. Le righe esistenti restano senza;
- la tabella `exercise_notes`, le note dell'utente sugli esercizi.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e8c1f5a3b7d2'
down_revision: Union[str, None] = 'd2b7e4a9c1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workout_sessions', sa.Column('client_id', sa.String(length=36), nullable=True))
    op.create_unique_constraint('uq_workout_sessions_client_id', 'workout_sessions', ['client_id'])
    op.add_column('session_sets', sa.Column('client_id', sa.String(length=36), nullable=True))
    op.create_unique_constraint('uq_session_sets_client_id', 'session_sets', ['client_id'])
    op.create_table(
        'exercise_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('profile_id', sa.Integer(), nullable=False),
        sa.Column('exercise_id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercises.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['profile_id'], ['user_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exercise_notes_profile_id', 'exercise_notes', ['profile_id'])
    op.create_index('ix_exercise_notes_exercise_id', 'exercise_notes', ['exercise_id'])
    op.create_index(
        'ix_exercise_note_profile_exercise', 'exercise_notes', ['profile_id', 'exercise_id'], unique=True
    )


def downgrade() -> None:
    op.drop_index('ix_exercise_note_profile_exercise', table_name='exercise_notes')
    op.drop_index('ix_exercise_notes_exercise_id', table_name='exercise_notes')
    op.drop_index('ix_exercise_notes_profile_id', table_name='exercise_notes')
    op.drop_table('exercise_notes')
    op.drop_constraint('uq_session_sets_client_id', 'session_sets', type_='unique')
    op.drop_column('session_sets', 'client_id')
    op.drop_constraint('uq_workout_sessions_client_id', 'workout_sessions', type_='unique')
    op.drop_column('workout_sessions', 'client_id')
