"""Create subscription_plans, user_subscriptions, and payments tables

Revision ID: f1a2b3c4d5e6
Revises: a73bb00612a0
Create Date: 2026-02-20 00:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'a73bb00612a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Use PL/pgSQL DO-blocks so types are created idempotently and SQLAlchemy's
    # event system never tries to re-emit CREATE TYPE during op.create_table.
    _enum_defs = {
        'subscription_status_enum': (
            'active', 'expired', 'cancelled', 'incomplete',
            'incomplete_expired', 'past_due', 'trialing', 'unpaid',
        ),
        'currency_enum': ('USD', 'EGP', 'EUR'),
        'payment_method_enum': ('card', 'wallet', 'bank_transfer'),
        'payment_gateway_enum': ('stripe', 'paymob', 'paypal'),
        'payment_status_enum': ('paid', 'pending', 'failed', 'refunded', 'cancelled'),
    }
    for name, values in _enum_defs.items():
        quoted = ', '.join(f"'{v}'" for v in values)
        op.execute(f"""
            DO $$ BEGIN
                CREATE TYPE {name} AS ENUM ({quoted});
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """)

    def _enum(name):
        # PgEnum with create_type=False is a bare type reference that never
        # emits CREATE TYPE, regardless of SQLAlchemy version.
        return PgEnum(name=name, create_type=False)

    # --- subscription_plans ---
    op.create_table(
        'subscription_plans',
        sa.Column('plan_id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )
    op.create_index('ix_subscription_plans_plan_id', 'subscription_plans', ['plan_id'])
    op.create_index('ix_subscription_plans_name', 'subscription_plans', ['name'], unique=True)

    # --- user_subscriptions ---
    op.create_table(
        'user_subscriptions',
        sa.Column('subscription_id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.user_id'),
            nullable=False,
        ),
        sa.Column(
            'plan_id',
            sa.Integer(),
            sa.ForeignKey('subscription_plans.plan_id'),
            nullable=False,
        ),
        sa.Column(
            'start_date',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'auto_renew',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
        ),
        sa.Column(
            'status',
            _enum('subscription_status_enum'),
            nullable=False,
            server_default='active',
        ),
    )
    op.create_index(
        'ix_user_subscriptions_subscription_id',
        'user_subscriptions',
        ['subscription_id'],
    )
    op.create_index('ix_user_subscriptions_user_id', 'user_subscriptions', ['user_id'])
    op.create_index('ix_user_subscriptions_plan_id', 'user_subscriptions', ['plan_id'])

    # --- payments ---
    op.create_table(
        'payments',
        sa.Column('payment_id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            'subscription_id',
            sa.Integer(),
            sa.ForeignKey('user_subscriptions.subscription_id'),
            nullable=False,
        ),
        sa.Column('amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', _enum('currency_enum'), nullable=False, server_default='USD'),
        sa.Column('payment_method', _enum('payment_method_enum'), nullable=False),
        sa.Column('payment_gateway', _enum('payment_gateway_enum'), nullable=False),
        sa.Column(
            'status',
            _enum('payment_status_enum'),
            nullable=False,
            server_default='pending',
        ),
        sa.Column(
            'transaction_id',
            sa.String(255),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            'payment_date',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'created_at',
            sa.DateTime(),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )
    op.create_index('ix_payments_payment_id', 'payments', ['payment_id'])
    op.create_index('ix_payments_subscription_id', 'payments', ['subscription_id'])
    op.create_index('ix_payments_transaction_id', 'payments', ['transaction_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_payments_transaction_id', table_name='payments')
    op.drop_index('ix_payments_subscription_id', table_name='payments')
    op.drop_index('ix_payments_payment_id', table_name='payments')
    op.drop_table('payments')

    op.drop_index('ix_user_subscriptions_plan_id', table_name='user_subscriptions')
    op.drop_index('ix_user_subscriptions_user_id', table_name='user_subscriptions')
    op.drop_index('ix_user_subscriptions_subscription_id', table_name='user_subscriptions')
    op.drop_table('user_subscriptions')

    op.drop_index('ix_subscription_plans_name', table_name='subscription_plans')
    op.drop_index('ix_subscription_plans_plan_id', table_name='subscription_plans')
    op.drop_table('subscription_plans')

    for name in (
        'payment_status_enum',
        'payment_gateway_enum',
        'payment_method_enum',
        'currency_enum',
        'subscription_status_enum',
    ):
        op.execute(f'DROP TYPE IF EXISTS {name}')
