"""Small source-clock tolerance for read-only local displays and reminders.

Observed cTrader timestamps can lead the local clock by about 0.1s.
This is not a change to broker draft/confirmation validation.
"""
SOURCE_CLOCK_SKEW_SECONDS = .25
