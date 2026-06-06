import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	test: {
		// Pure-logic unit tests live next to the code as *.test.ts.
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'node'
	}
});
