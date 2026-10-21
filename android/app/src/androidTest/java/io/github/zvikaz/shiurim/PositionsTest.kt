package io.github.zvikaz.shiurim

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PositionsTest {
    private val preferences by lazy {
        InstrumentationRegistry.getInstrumentation().targetContext
            .getSharedPreferences("positions-test", 0)
    }
    private lateinit var positions: Positions

    @Before
    fun setUp() {
        preferences.edit().clear().commit()
        positions = Positions(preferences)
    }

    @After
    fun tearDown() {
        preferences.edit().clear().commit()
    }

    @Test
    fun heardIsDurableAndDismissIsIndependent() {
        positions.save("series/not-quite-finished", 94_999, 100_000)
        assertFalse(positions.progress("series/not-quite-finished")!!.finished)

        positions.save("series/1", 95_000, 100_000)
        assertTrue(positions.progress("series/1")!!.finished)

        positions.save("series/1", 5_000, 100_000)
        assertTrue(positions.progress("series/1")!!.finished)

        positions.dismiss("series/1")
        assertEquals(emptyList<String>(), positions.recent())
        assertTrue(positions.progress("series/1")!!.finished)

        positions.save("series/1", 6_000, 100_000)
        assertEquals(listOf("series/1"), positions.recent())
    }

    @Test
    fun anEntireSeriesCanBeMarkedHeard() {
        positions.save("series/2", 12_000, 100_000)
        positions.finishedSeries("series", 3)

        assertTrue((1..3).all { positions.progress("series/$it")!!.finished })
        assertEquals(listOf("series/3"), positions.recent())
        assertFalse(positions.progress("series/2") == null)
    }
}
