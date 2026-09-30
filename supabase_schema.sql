-- SQL Schema for Supabase to match the local Inventory Management System
-- Run this in the Supabase SQL Editor

-- 1. Users table
CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    last_modified TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 2. Products table
CREATE TABLE IF NOT EXISTS public.products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    sku VARCHAR(100) UNIQUE NOT NULL,
    category VARCHAR(100),
    price FLOAT DEFAULT 0.0,
    sale_price FLOAT DEFAULT 0.0,
    cost_price FLOAT DEFAULT 0.0,
    stock_qty FLOAT DEFAULT 0.0,
    is_active BOOLEAN DEFAULT TRUE,
    unit_type VARCHAR(20) DEFAULT 'piece',
    base_unit_price FLOAT DEFAULT 0.0,
    extra_fields JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    last_modified TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 3. Invoices table
CREATE TABLE IF NOT EXISTS public.invoices (
    id SERIAL PRIMARY KEY,
    number VARCHAR(50) UNIQUE NOT NULL,
    user_id INTEGER REFERENCES public.users(id),
    customer_uid VARCHAR(100),
    customer_name VARCHAR(200),
    total_amount FLOAT DEFAULT 0.0,
    discount_percent FLOAT DEFAULT 0.0,
    discount_fixed FLOAT DEFAULT 0.0,
    tax_percent FLOAT DEFAULT 0.0,
    tax_amount FLOAT DEFAULT 0.0,
    net_amount FLOAT DEFAULT 0.0,
    payment_method VARCHAR(50) DEFAULT 'Cash',
    payment_account VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    last_modified TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 4. Invoice Items table
CREATE TABLE IF NOT EXISTS public.invoice_items (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES public.invoices(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES public.products(id),
    quantity FLOAT DEFAULT 1.0,
    quantity_exact FLOAT DEFAULT 1.0,
    unit_type VARCHAR(20) DEFAULT 'piece',
    unit_price FLOAT DEFAULT 0.0,
    total_price FLOAT DEFAULT 0.0,
    cost_price FLOAT DEFAULT 0.0,
    default_sale_price FLOAT DEFAULT 0.0,
    actual_sale_price FLOAT DEFAULT 0.0,
    profit FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    last_modified TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 5. Stock Transactions table
CREATE TABLE IF NOT EXISTS public.stock_transactions (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES public.products(id) ON DELETE CASCADE,
    change_qty FLOAT DEFAULT 0.0,
    remaining_stock FLOAT DEFAULT 0.0,
    reason VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    last_modified TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 6. Expenses table
CREATE TABLE IF NOT EXISTS public.expenses (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    amount FLOAT NOT NULL DEFAULT 0.0,
    category VARCHAR(100) DEFAULT 'General',
    notes TEXT,
    date TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    last_modified TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 7. License table (for license manager)
CREATE TABLE IF NOT EXISTS public.license (
    id SERIAL PRIMARY KEY,
    installation_id VARCHAR(255) UNIQUE NOT NULL,
    status BOOLEAN DEFAULT TRUE,
    valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Enable RLS (Optional, but recommended. For now, we'll keep it simple as the app uses Service/Anon key)
-- ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
-- ... repeat for other tables if needed

-- Add a default admin license for testing if needed
-- INSERT INTO public.license (installation_id, status, valid_until) VALUES ('test-id', true, '2025-12-31');
