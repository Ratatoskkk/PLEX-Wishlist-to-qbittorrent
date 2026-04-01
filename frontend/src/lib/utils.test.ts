import { describe, it, expect } from 'vitest';
import { formatSize, formatTime } from './utils';

describe('formatSize', () => {
  it('should return "0 B" for 0 bytes', () => {
    expect(formatSize(0)).toBe('0 B');
  });

  it('should format bytes correctly', () => {
    expect(formatSize(500)).toBe('500 B');
    expect(formatSize(1023)).toBe('1023 B');
  });

  it('should format kilobytes correctly', () => {
    expect(formatSize(1024)).toBe('1 KB');
    expect(formatSize(1536)).toBe('1.5 KB');
  });

  it('should format megabytes correctly', () => {
    expect(formatSize(1048576)).toBe('1 MB');
    expect(formatSize(2097152)).toBe('2 MB');
  });

  it('should format gigabytes correctly', () => {
    expect(formatSize(1073741824)).toBe('1 GB');
    expect(formatSize(1610612736)).toBe('1.5 GB');
  });

  it('should format terabytes correctly', () => {
    expect(formatSize(1099511627776)).toBe('1 TB');
  });

  it('should round to 2 decimal places', () => {
    expect(formatSize(1234)).toBe('1.21 KB');
    expect(formatSize(1234567)).toBe('1.18 MB');
  });
});

describe('formatTime', () => {
  it('should return "∞" for negative inputs', () => {
    expect(formatTime(-1)).toBe('∞');
    expect(formatTime(-100)).toBe('∞');
  });

  it('should return "∞" for inputs >= 8640000', () => {
    expect(formatTime(8640000)).toBe('∞');
    expect(formatTime(10000000)).toBe('∞');
  });

  it('should format seconds correctly', () => {
    expect(formatTime(0)).toBe('0s');
    expect(formatTime(45)).toBe('45s');
    expect(formatTime(59)).toBe('59s');
  });

  it('should format minutes and seconds correctly', () => {
    expect(formatTime(60)).toBe('1m 0s');
    expect(formatTime(90)).toBe('1m 30s');
    expect(formatTime(3599)).toBe('59m 59s');
  });

  it('should format hours and minutes correctly', () => {
    expect(formatTime(3600)).toBe('1h 0m');
    expect(formatTime(3660)).toBe('1h 1m');
    expect(formatTime(7325)).toBe('2h 2m');
    expect(formatTime(8639999)).toBe('2399h 59m');
  });
});
