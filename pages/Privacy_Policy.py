import streamlit as st

st.set_page_config(page_title="Privacy Policy — Hoopes Overdog", page_icon="🔒")

st.markdown("""
# Hoopes Overdog — Privacy Policy
*Last updated: July 2026*

Hoopes Overdog is a Chrome extension that overlays live, simulation-based draft
recommendations on your own Underdog Fantasy best ball draft. This page describes what
data the extension handles, why, and what happens to it.

## What the extension reads

While you have an Underdog draft page open, the extension reads data already present on
that page — pick history and player information — in order to compute recommendations. It
does this by observing network requests the page itself makes and by reading page content
directly. This is limited strictly to `underdogsports.com` and its subdomains; the
extension takes no action and reads nothing on any other website.

## What information you may provide

The extension can optionally use your Underdog username to identify which draft entry is
yours, so it can start showing recommendations without waiting for your first pick. This is
entirely optional — a manual "this is my turn" button provides the same result without
typing anything.

If you do enter it, your username is stored locally in Chrome's extension storage
(`chrome.storage.local`) on your own device. It is used solely to match you against your
draft's own entry list.

## What is never collected

The extension does not collect your name, email address, physical address, payment
information, passwords, or any authentication credentials. It has no login system of its
own. It does not track which other websites you visit, and it does not monitor clicks,
scrolling, mouse movement, or keystrokes.

## Where your data goes

Nowhere. Everything the extension reads or stores — including your optional username and
your saved equity-weight and draft-format settings — stays on your own device. Nothing is
transmitted to any server operated by the developer, to Underdog, or to any third party.
All recommendation calculations run locally in your own browser.

## How this data is used

Solely to provide the extension's one function: computing and displaying draft
recommendations for your own draft, in your own browser, while you're using it. Nothing is
used for advertising, profiling, analytics, or any purpose beyond that.

## Changes to this policy

If what the extension collects or how it's used ever changes, this page will be updated to
reflect that before any such change ships.

## Contact

Questions about this policy can be directed to the contact email listed on the extension's
Chrome Web Store listing.
""")

